package kr.demo.visualguide

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import javax.net.ssl.HttpsURLConnection

class CloudApiException(message: String) : Exception(message)

class CloudApiClient(
    val endpoint: ApiEndpoint, private val token: String? = null,
    private val connections: (java.net.URL) -> HttpsURLConnection = { it.openConnection() as HttpsURLConnection },
) {
    init { require(token == null || token.length in 16..4096 && token.all { it.code in 33..126 }) }
    suspend fun pair(code: String): DeviceRegistration {
        require(code.length in CloudContractLimits.MIN_PAIRING_CODE..CloudContractLimits.MAX_PAIRING_CODE &&
            code.none { it.isISOControl() }) { "페어링 코드는 제어문자 없이 8~256자여야 합니다." }
        return CloudDtos.pairing(json("/v1/pair", JSONObject().put("code", code), false),
            endpoint, System.currentTimeMillis())
    }
    suspend fun catalog() = CloudDtos.catalog(json("/v1/catalog"))
    suspend fun guide(id: String) = CloudDtos.guide(json("/v1/guides/${identifier(id)}"))
    suspend fun model(id: String) = CloudDtos.model(json("/v1/models/${identifier(id)}"), endpoint)
    suspend fun session(id: String) = CloudDtos.session(json("/v1/sessions/${identifier(id)}"))
    suspend fun start(guideId: String) = CloudDtos.session(json("/v1/sessions",
        JSONObject().put("guide_id", identifier(guideId))))
    suspend fun advance(sessionId: String, event: CloudEvent) = CloudDtos.session(
        json("/v1/sessions/${identifier(sessionId)}/events", event.json()))
    suspend fun reference(model: CloudModel): ByteArray =
        request(endpoint.reference(model.id, model.referencePath), null, true, 8 * 1024 * 1024, true)

    suspend fun identify(category: String, kind: String, jpeg: ByteArray, ocr: String,
                         catalog: List<CloudGuide>): Identification {
        require(category in listOf("aircon", "tv", "airdresser") && kind in listOf("body", "remote", "screen"))
        validateImage(jpeg)
        val body = JSONObject().put("category", category).put("target_kind", kind)
            .put("image_base64", Base64.encodeToString(jpeg, Base64.NO_WRAP)).put("ocr_text", ocr.take(2048))
        return CloudDtos.identification(json("/v1/identify", body), catalog)
    }
    suspend fun verify(sessionId: String, stepId: String, jpeg: ByteArray): CloudVerification {
        validateImage(jpeg)
        val body = JSONObject().put("step_id", identifier(stepId))
            .put("image_base64", Base64.encodeToString(jpeg, Base64.NO_WRAP))
        return CloudDtos.verification(json("/v1/sessions/${identifier(sessionId)}/verify", body), stepId)
    }
    private fun validateImage(bytes: ByteArray) {
        require(bytes.isNotEmpty() && bytes.size <= 2 * 1024 * 1024) { "사진은 2MiB 이하여야 합니다." }
    }
    private suspend fun json(path: String, body: JSONObject? = null, authenticated: Boolean = true): JSONObject {
        val bytes = body?.toString()?.toByteArray(Charsets.UTF_8)
        require(bytes == null || bytes.size <= 3 * 1024 * 1024)
        val response = request(endpoint.api(path), bytes, authenticated, 1024 * 1024)
        return try { JSONObject(response.toString(Charsets.UTF_8)) } catch (_: Exception) {
            throw CloudApiException("서버 JSON 응답 형식이 올바르지 않습니다.")
        }
    }
    private suspend fun request(
        url: java.net.URL, body: ByteArray?, authenticated: Boolean, maxBytes: Int, image: Boolean = false,
    ): ByteArray = withContext(Dispatchers.IO) {
        currentCoroutineContext().ensureActive()
        val connection = connections(url)
        try {
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 15_000
            connection.readTimeout = 90_000
            connection.requestMethod = if (body == null) "GET" else "POST"
            connection.setRequestProperty("Accept", if (image) "image/png,image/jpeg" else "application/json")
            if (authenticated) {
                require(!token.isNullOrBlank()) { "단말 페어링이 필요합니다." }
                connection.setRequestProperty("Authorization", "Bearer $token")
            }
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.setFixedLengthStreamingMode(body.size)
                connection.outputStream.use { it.write(body) }
            }
            val status = connection.responseCode
            if (status !in 200..299) {
                val meaning = when (status) {
                    401 -> "인증/페어링이 만료되었거나 거부되었습니다."
                    404 -> "등록된 대상 또는 소유 세션을 찾을 수 없습니다."
                    409 -> "현재 단계 또는 이벤트 충돌입니다. 세션을 새로고침하세요."
                    413 -> "입력 크기 제한을 초과했습니다."
                    429 -> "요청이 많습니다. 잠시 후 같은 요청을 재시도하세요."
                    503 -> "클라우드 의존 서비스가 준비되지 않았습니다."
                    504 -> "서버 처리 시간이 초과되었습니다."
                    in 300..399 -> "리디렉션을 거부했습니다. API 원점을 확인하세요."
                    else -> "클라우드 요청이 실패했습니다."
                }
                throw CloudApiException("HTTP $status: $meaning")
            }
            val mime = connection.contentType?.substringBefore(';')?.lowercase()
            require(if (image) mime in listOf("image/png", "image/jpeg") else mime == "application/json") {
                "서버 콘텐츠 형식이 계약과 다릅니다."
            }
            val result = connection.inputStream.use { readBounded(it, maxBytes) }
            currentCoroutineContext().ensureActive()
            result
        } finally { connection.disconnect() }
    }
    private fun readBounded(input: InputStream, max: Int): ByteArray {
        val result = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            require(result.size() + count <= max) { "서버 응답 크기 제한을 초과했습니다." }
            result.write(buffer, 0, count)
        }
        return result.toByteArray()
    }
}
