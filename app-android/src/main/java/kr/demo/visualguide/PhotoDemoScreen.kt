package kr.demo.visualguide

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.IOException

@Composable
internal fun PhotoDemoScreen(activity: ComponentActivity, leave: () -> Unit) {
    val catalog = remember { runCatching { PhotoDemoCatalog.load(activity) } }
    val products = catalog.getOrNull()
    if (products == null) {
        Column(Modifier.padding(20.dp)) {
            Text("사진 참조 카탈로그 오류: ${catalog.exceptionOrNull()?.message}",
                color = MaterialTheme.colorScheme.error)
            OutlinedButton(onClick = leave) { Text("모드 선택으로") }
        }
        return
    }
    var model by remember { mutableStateOf(products.first()) }
    var state by remember { mutableStateOf(PhotoDemoState()) }
    var photo by remember { mutableStateOf<Bitmap?>(null) }
    var error by remember { mutableStateOf("") }
    var generation by remember { mutableIntStateOf(0) }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    fun clear() {
        generation++; state = PhotoDemoState(); photo = null; error = ""; loading = false
    }
    fun open(url: String) {
        try {
            activity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: ActivityNotFoundException) {
            error = "공식 페이지를 열 브라우저가 없습니다."
        }
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) {
            clear()
            val request = generation
            loading = true
            fun failed(message: String?) {
                if (generation == request) {
                    loading = false; error = "사진 읽기 실패: $message"
                }
            }
            scope.launch {
                try {
                    val bitmap = withContext(Dispatchers.IO) { loadLocalPhoto(activity, uri) }
                    if (generation == request) {
                        photo = bitmap; state = PhotoDemoState(hasPhoto = true); loading = false
                    }
                } catch (exception: IOException) {
                    failed(exception.message)
                } catch (exception: SecurityException) {
                    failed(exception.message)
                } catch (exception: IllegalArgumentException) {
                    failed(exception.message)
                }
            }
        }
    }
    Column(Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("실모델 사진 참조 DEMO · 2종", style = MaterialTheme.typography.headlineSmall)
        Text("카메라·자동 모델 인식·AR 정합·고장 진단이 아닙니다. 공식 사진은 내장하지 않았습니다. 사진은 메모리에서만 사용하고 서버에 보내거나 보관하지 않습니다.")
        products.forEach { product ->
            OutlinedButton(onClick = { clear(); model = product }) {
                Text("${product.category} · ${product.model}")
            }
        }
        Text("${model.name}\n${model.model}", style = MaterialTheme.typography.titleMedium)
        OutlinedButton(onClick = { open(model.photoSourceUrl) }) { Text("공식 사진 원본 페이지") }
        OutlinedButton(onClick = { picker.launch("image/*") }, enabled = !loading) {
            Text(if (loading) "사진 읽는 중" else "사용권 있는 로컬 사진 선택")
        }
        Text("JPEG/PNG 최대 10 MiB·20 MP. 사진 또는 모델을 바꾸면 확인·결과를 지웁니다.")
        if (error.isNotEmpty()) Text(error, color = MaterialTheme.colorScheme.error)
        photo?.let { bitmap ->
            Image(bitmap.asImageBitmap(), "사용자가 불러온 사진 · 모델 자동 검증 안 됨",
                Modifier.fillMaxWidth().heightIn(max = 400.dp))
        }
        Row {
            Checkbox(state.rightsConfirmed, enabled = state.hasPhoto, onCheckedChange = {
                state = state.copy(rightsConfirmed = it, started = false, outcome = null)
            })
            Text("이 사진의 사용권을 확인했습니다.")
        }
        Row {
            Checkbox(state.identityConfirmed, enabled = state.hasPhoto, onCheckedChange = {
                state = state.copy(identityConfirmed = it, started = false, outcome = null)
            })
            Text("사진 모델명이 ${model.model}과 일치함을 직접 확인했습니다. 자동 인식이 아닙니다.")
        }
        Button(onClick = { state = state.start() }, enabled = state.canStart) { Text("사진 참조 안내 시작") }
        OutlinedButton(onClick = { clear(); error = "모델 미확인: 안내 차단" }, enabled = state.hasPhoto) {
            Text("다른 모델 또는 모델을 모르겠어요")
        }
        if (state.started) {
            Card {
                Column(Modifier.padding(12.dp)) {
                    Text("사진 참조 안내 카드 · AR 추적 아님")
                    Text(model.issue)
                    Text("실제 버튼 좌표·절차는 미검수이므로 표시하지 않습니다. 공식 모델 지원에서 사용 설명서와 문제 해결 자료를 확인하세요.")
                }
            }
            OutlinedButton(onClick = { open(model.supportUrl) }) { Text("이 모델 공식 지원 열기") }
            for (outcome in listOf("미해결", "판정 불가", "사용자가 해결되었다고 보고")) {
                OutlinedButton(onClick = { state = state.report(outcome) }) { Text(outcome) }
            }
        }
        Text(state.outcome?.let { "사용자 수동 보고: $it · 실제 고장 해결 자동 검증 없음" } ?: "미판정")
        Text("위험 징후가 있으면 사용을 중단하고 공식 지원을 이용하세요. 미검수 절차나 실제 버튼 좌표를 임의로 적용하지 않습니다.")
        OutlinedButton(onClick = { clear() }) { Text("사진·확인·결과 지우기") }
        OutlinedButton(onClick = leave) { Text("모드 선택으로") }
    }
}

private fun loadLocalPhoto(context: Context, uri: Uri): Bitmap {
    require(uri.scheme == "content") { "로컬 사진 선택기를 사용하세요." }
    val limit = 10 * 1024 * 1024
    val buffer = ByteArray(limit + 1)
    var size = 0
    context.contentResolver.openInputStream(uri)?.use { stream ->
        while (size < buffer.size) {
            val count = stream.read(buffer, size, buffer.size - size)
            if (count == -1) break
            if (count == 0) throw IOException("사진 스트림을 읽을 수 없습니다.")
            size += count
        }
    } ?: throw IOException("사진을 열 수 없습니다.")
    require(size in 1..limit) { "사진은 10 MiB 이하여야 합니다." }
    val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(buffer, 0, size, options)
    require(options.outMimeType in setOf("image/jpeg", "image/png")) { "JPEG/PNG만 허용합니다." }
    options.inSampleSize = photoSampleSize(options.outWidth, options.outHeight)
    options.inJustDecodeBounds = false
    return BitmapFactory.decodeByteArray(buffer, 0, size, options)
        ?: throw IllegalArgumentException("사진을 해석할 수 없습니다.")
}
