package kr.demo.visualguide

import kr.demo.guide.NormalizedRect
import org.json.JSONObject
import java.net.URI
import java.net.URL
import java.util.UUID

object CloudContractLimits {
    const val MIN_PAIRING_CODE = 8
    const val MAX_PAIRING_CODE = 256
    const val MAX_GUIDE_TITLE = 500
    const val MAX_GUIDE_STEPS = 128
}

class ApiEndpoint private constructor(val origin: String) {
    fun api(path: String): URL {
        require(path.startsWith("/v1/") && !path.contains("..") && !path.contains('?') && !path.contains('#'))
        return URI(origin + path).toURL()
    }
    fun reference(targetId: String, path: String): URL {
        require(path == "/v1/models/${identifier(targetId)}/reference") {
            "참조 이미지는 같은 API 원점의 등록된 상대 경로여야 합니다."
        }
        return api(path)
    }
    companion object {
        fun parse(value: String): ApiEndpoint {
            val uri = try { URI(value.trim()) } catch (_: Exception) {
                throw IllegalArgumentException("HTTPS API 원점 주소가 필요합니다.")
            }
            require(uri.scheme.equals("https", true) && !uri.host.isNullOrBlank() &&
                uri.userInfo == null && uri.rawQuery == null && uri.rawFragment == null &&
                uri.rawPath in listOf("", "/") && uri.port in -1..65535 && uri.port != 0) {
                "HTTPS 원점만 허용합니다. 사용자 정보, 경로, 쿼리, 프래그먼트를 제거하세요."
            }
            val host = uri.host.lowercase()
            val authority = if (host.contains(':') && !host.startsWith('[')) "[$host]" else host
            return ApiEndpoint("https://$authority" + if (uri.port == -1 || uri.port == 443) "" else ":${uri.port}")
        }
    }
}

fun identifier(value: String): String {
    require(value.matches(Regex("[A-Za-z0-9_-]{1,80}"))) { "잘못된 등록 식별자입니다." }
    return value
}

data class CloudStep(val id: String, val buttonId: String, val instruction: String, val expected: String)
data class CloudGuide(val id: String, val targetId: String, val title: String, val demo: Boolean, val steps: List<CloudStep>)
data class CloudModel(
    val id: String, val physicalWidth: Float, val referencePath: String,
    val imageWidth: Int, val imageHeight: Int,
    val display: NormalizedRect, val buttons: Map<String, NormalizedRect>,
) {
    fun validate(guide: CloudGuide) {
        require(id == guide.targetId && guide.steps.all { buttons.containsKey(it.buttonId) }) {
            "가이드와 등록된 버튼 지도가 일치하지 않습니다."
        }
    }
}
data class CloudSession(
    val id: String, val guideId: String, val stepIndex: Int, val currentStepId: String?,
    val finished: Boolean, val demo: Boolean, val lastSource: String?,
) {
    fun validate(guide: CloudGuide) {
        require(guideId == guide.id && demo == guide.demo && stepIndex in 0..guide.steps.size &&
            finished == (stepIndex == guide.steps.size) &&
            currentStepId == guide.steps.getOrNull(stepIndex)?.id) { "서버 세션과 가이드의 현재 단계가 일치하지 않습니다." }
    }
}
data class DeviceRegistration(
    val origin: String, val token: String, val expiresAtMs: Long, val deviceId: String,
    val sessionId: String? = null, val pending: CloudEvent? = null,
)
data class CloudEvent(
    val eventId: String, val stepId: String, val source: String,
    val observedText: String? = null, val verificationId: String? = null,
) {
    init {
        require(UUID.fromString(eventId).toString() == eventId)
        identifier(stepId)
        require(source in listOf("manual", "ocr", "vlm"))
        require(observedText == null || observedText.length <= 2048)
        require(source != "ocr" || !observedText.isNullOrBlank())
        require(source != "vlm" || !verificationId.isNullOrBlank())
    }
    fun json(): JSONObject = JSONObject().put("event_id", eventId).put("step_id", stepId)
        .put("source", source).put("observed_text", observedText ?: JSONObject.NULL)
        .put("verification_id", verificationId ?: JSONObject.NULL)
}
data class CloudCandidate(
    val productId: String, val model: String, val targetId: String,
    val guideIds: List<String>, val score: Double, val demo: Boolean,
)
data class Identification(val status: String, val candidates: List<CloudCandidate>, val provider: String)
data class CloudVerification(
    val status: String, val stepId: String, val reason: String, val proof: String?, val deployment: String,
)

object CloudDtos {
    private fun JSONObject.string(key: String, max: Int = 2048): String =
        (get(key) as? String)?.also { require(it.isNotBlank() && it.length <= max) }
            ?: throw IllegalArgumentException("문자열 필드 오류: $key")
    private fun JSONObject.bool(key: String): Boolean =
        get(key) as? Boolean ?: throw IllegalArgumentException("불리언 필드 오류: $key")
    private fun JSONObject.integer(key: String): Int {
        val number = get(key) as? Number ?: throw IllegalArgumentException("숫자 필드 오류: $key")
        val value = number.toDouble()
        require(value.isFinite() && value == value.toInt().toDouble())
        return value.toInt()
    }
    private fun JSONObject.nullable(key: String): String? = if (isNull(key)) null else string(key)
    private fun rect(json: JSONObject): NormalizedRect = NormalizedRect(
        json.getDouble("left").toFloat(), json.getDouble("top").toFloat(),
        json.getDouble("right").toFloat(), json.getDouble("bottom").toFloat(),
    )
    fun guide(json: JSONObject): CloudGuide {
        val entries = json.getJSONArray("steps")
        require(entries.length() in 1..CloudContractLimits.MAX_GUIDE_STEPS)
        val steps = (0 until entries.length()).map {
            val step = entries.getJSONObject(it)
            CloudStep(identifier(step.string("id")), identifier(step.string("button_id")),
                step.string("instruction"), step.string("expected_display", 256))
        }
        require(steps.map { it.id }.distinct().size == steps.size)
        return CloudGuide(identifier(json.string("id")), identifier(json.string("target_id")),
            json.string("title", CloudContractLimits.MAX_GUIDE_TITLE), json.bool("demo"), steps)
    }
    fun catalog(json: JSONObject): List<CloudGuide> {
        val entries = json.getJSONArray("guides")
        require(entries.length() <= 200)
        return (0 until entries.length()).map { guide(entries.getJSONObject(it)) }.also {
            require(it.map { guide -> guide.id }.distinct().size == it.size)
        }
    }
    fun model(json: JSONObject, endpoint: ApiEndpoint): CloudModel {
        val id = identifier(json.string("id"))
        val path = json.string("reference_image_url")
        endpoint.reference(id, path)
        val physical = json.getDouble("reference_width_m").toFloat()
        require(physical.isFinite() && physical in 0.001f..10f)
        val width = json.integer("image_width")
        val height = json.integer("image_height")
        require(width in 1..4096 && height in 1..4096 && width.toLong() * height <= 8_388_608)
        val buttons = json.getJSONObject("buttons")
        require(buttons.length() in 1..100)
        return CloudModel(id, physical, path, width, height, rect(json.getJSONObject("display")),
            buttons.keys().asSequence().associate { identifier(it) to rect(buttons.getJSONObject(it)) })
    }
    fun session(json: JSONObject): CloudSession {
        val source = json.nullable("last_source")
        require(source == null || source in listOf("manual", "ocr", "vlm"))
        return CloudSession(identifier(json.string("id")), identifier(json.string("guide_id")),
            json.integer("step_index"), json.nullable("current_step_id"), json.bool("finished"),
            json.bool("demo"), source)
    }
    fun pairing(json: JSONObject, endpoint: ApiEndpoint, nowMs: Long): DeviceRegistration {
        require(json.string("token_type") == "Bearer" && json.string("scope") == "device")
        val token = json.string("access_token", 4096)
        require(token.length >= 16 && token.all { it.code in 33..126 })
        val seconds = json.integer("expires_in")
        require(seconds in 1..31_536_000)
        return DeviceRegistration(endpoint.origin, token, nowMs + seconds * 1000L,
            identifier(json.string("device_id")))
    }
    fun event(json: JSONObject) = CloudEvent(json.string("event_id"), json.string("step_id"),
        json.string("source"), json.nullable("observed_text"), json.nullable("verification_id"))

    fun identification(json: JSONObject, catalog: List<CloudGuide>): Identification {
        val status = json.string("status")
        val confirm = json.bool("requires_confirmation")
        val candidates = json.getJSONArray("candidates")
        require(candidates.length() <= 20)
        if (status == "unknown") {
            require(!confirm && candidates.length() == 0)
            return Identification(status, emptyList(), json.string("provider", 256))
        }
        require(status == "candidates" && confirm && candidates.length() > 0)
        val parsed = (0 until candidates.length()).map { index ->
            val entry = candidates.getJSONObject(index)
            val targetId = identifier(entry.string("target_id"))
            val guideIds = entry.getJSONArray("guide_ids")
            require(guideIds.length() in 1..100)
            val ids = (0 until guideIds.length()).map { identifier(guideIds.getString(it)) }
            val demo = entry.bool("demo")
            require(ids.all { id -> catalog.any { it.id == id && it.targetId == targetId && it.demo == demo } }) {
                "식별 응답에 게시된 카탈로그에 없는 대상이 포함되어 있습니다."
            }
            val score = entry.getDouble("search_score")
            require(score.isFinite())
            CloudCandidate(identifier(entry.string("product_id")), entry.string("model", 256),
                targetId, ids, score, demo)
        }
        return Identification(status, parsed, json.string("provider", 256))
    }
    fun verification(json: JSONObject, stepId: String): CloudVerification {
        val status = json.string("status")
        require(status in listOf("pass", "fail", "unsure") && json.string("step_id") == stepId)
        val proof = json.nullable("verification_id")
        if (status == "pass") {
            require(!proof.isNullOrBlank() && json.integer("expires_in") > 0)
        } else require(proof == null)
        return CloudVerification(status, stepId, json.string("reason"), proof, json.string("model_deployment", 128))
    }
}
