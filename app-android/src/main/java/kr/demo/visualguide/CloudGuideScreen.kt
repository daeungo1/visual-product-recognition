package kr.demo.visualguide

import androidx.activity.ComponentActivity
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun CloudGuideScreen(activity: ComponentActivity, leave: () -> Unit) {
    val scope = rememberCoroutineScope()
    val coordinator = remember { CloudCoordinator(SecureDeviceStore(activity), scope) }
    val state = coordinator.state
    var url by remember { mutableStateOf(BuildConfig.API_BASE_URL) }
    var code by remember { mutableStateOf("") }
    val validCode = code.length in CloudContractLimits.MIN_PAIRING_CODE..CloudContractLimits.MAX_PAIRING_CODE &&
        code.none { it.isISOControl() }
    var photoConsent by remember { mutableStateOf(false) }
    var cameraGeneration by remember { mutableIntStateOf(0) }
    var showCatalog by remember { mutableStateOf(false) }
    var voice by remember { mutableStateOf(false) }
    var voiceReady by remember { mutableStateOf(false) }
    var voiceStatus by remember { mutableStateOf("한국어 음성 초기화 중") }
    val speech = remember {
        AndroidSpeech(activity) { message, ready ->
            activity.runOnUiThread { voiceStatus = message; voiceReady = ready }
        }
    }
    val owner = LocalLifecycleOwner.current
    LaunchedEffect(Unit) { coordinator.initialize() }
    LaunchedEffect(state.savedOrigin) {
        if (state.savedOrigin.isNotBlank()) url = state.savedOrigin
        photoConsent = false
    }
    LaunchedEffect(state.session?.id, state.session?.currentStepId, voice, voiceReady) {
        if (voice && voiceReady && state.session != null) {
            speech.speak(state.step?.instruction ?: "서버에서 가이드 완료를 승인했습니다.")
        } else speech.stop()
    }
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE) { coordinator.pause(); speech.stop() }
        }
        owner.lifecycle.addObserver(observer)
        onDispose {
            owner.lifecycle.removeObserver(observer)
            coordinator.pause()
            speech.close()
        }
    }
    AdaptiveGuideLayout(camera = { modifier ->
        Column(modifier.background(Color.Black)) {
            Text(
                if (state.guide?.demo == true) "HTTPS · 등록 합성 DEMO"
                else if (state.guide != null) "HTTPS · 사용자 확인 등록 대상" else "HTTPS · 등록 대상 선택 전",
                color = Color.White, modifier = Modifier.padding(6.dp),
                style = MaterialTheme.typography.bodySmall,
            )
            Box(Modifier.fillMaxWidth().weight(1f)) {
                CameraPermissionHost(activity, state.target, coordinator.cameraRequest, cameraGeneration,
                    coordinator::onFrame, coordinator::onOcr, coordinator::cameraStatus,
                    coordinator::ocrStatus, coordinator.snapshots)
                val polygon = if (state.overlay.fullTracking && state.overlay.scope == coordinator.captureScope)
                    state.overlay.polygon else emptyList()
                Canvas(Modifier.fillMaxSize()) {
                    if (polygon.size == 4) {
                        val path = Path().apply {
                            moveTo(polygon[0].x, polygon[0].y)
                            polygon.drop(1).forEach { lineTo(it.x, it.y) }
                            close()
                        }
                        drawPath(path, Color.Yellow.copy(alpha = 0.25f))
                        drawPath(path, Color.Yellow, style = Stroke(4.dp.toPx()))
                    }
                }
            }
        }
    }, controls = { modifier ->
        Column(modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("실제 HTTPS 연결 모드", style = MaterialTheme.typography.titleLarge)
            Text("연결 오류를 DEMO 성공으로 바꾸지 않습니다. 실제 삼성 자산은 승인된 서버 등록이 있어야 합니다.")
            OutlinedTextField(url, onValueChange = { url = it }, singleLine = true,
                enabled = !state.busy && !state.registered,
                label = { Text("HTTPS API 원점 URL") }, modifier = Modifier.fillMaxWidth())
            if (BuildConfig.API_BASE_URL.isBlank() && url.isBlank()) {
                Text("빌드 기본 URL 미설정. 실제 배포 HTTPS 원점을 입력하세요.")
            }
            OutlinedTextField(code, onValueChange = { code = it }, singleLine = true,
                enabled = !state.busy, visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                isError = code.isNotEmpty() && !validCode,
                supportingText = { Text("운영자 코드 8~256자. 제어문자는 허용하지 않습니다.") },
                label = { Text("운영자 발급 일회용 페어링 코드") }, modifier = Modifier.fillMaxWidth())
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Button(onClick = {
                    val oneTimeCode = code
                    code = ""
                    coordinator.pairAndConnect(url, oneTimeCode)
                }, enabled = !state.busy && validCode && url.isNotBlank()) { Text("페어링 · 연결") }
                OutlinedButton(onClick = { coordinator.connectSaved(url) },
                    enabled = !state.busy && state.registered) { Text("저장 단말 · 세션 복원") }
                OutlinedButton(onClick = { code = ""; coordinator.forget() }, enabled = !state.busy) {
                    Text("저장 단말 삭제 · 서버 주소 변경")
                }
            }
            Text("삭제는 이 기기의 암호화 등록/세션만 지웁니다. 서버 토큰 회수는 운영자가 관리합니다.",
                style = MaterialTheme.typography.bodySmall)
            Text(if (state.connected) "HTTPS 인증 카탈로그 연결됨" else "클라우드 연결 미완료")
            Text(state.message)
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            if (state.busy) Text("처리 중 · 서버 응답 전에는 진행하지 않습니다.")
            Text(state.cameraStatus, style = MaterialTheme.typography.bodySmall)
            Text(state.overlay.message, style = MaterialTheme.typography.bodySmall)
            if (state.connected) {
                OutlinedButton(onClick = coordinator::forgetSession, enabled = !state.busy) {
                    Text("저장 세션 포기 · 새 가이드 선택")
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("aircon" to "에어컨", "tv" to "TV", "airdresser" to "에어드레서").forEach { (id, title) ->
                        OutlinedButton(onClick = { coordinator.setCategory(id) }, enabled = !state.busy) {
                            Text((if (state.category == id) "✓ " else "") + title)
                        }
                    }
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("remote" to "리모컨", "body" to "본체", "screen" to "화면").forEach { (id, title) ->
                        OutlinedButton(onClick = { coordinator.setKind(id) }, enabled = !state.busy) {
                            Text((if (state.kind == id) "✓ " else "") + title)
                        }
                    }
                }
                FlowRow {
                    Checkbox(photoConsent, { photoConsent = it }, enabled = !state.busy)
                    Text("사진 1장씩 HTTPS 전송에 동의", Modifier.padding(top = 12.dp))
                }
                Text("식별/AI 확인 버튼을 누를 때만 최대 1024px·2MiB JPEG 1장을 보냅니다. 앱은 사진을 파일로 저장하지 않습니다. 서버 보관 정책은 운영자에게 확인하세요.",
                    style = MaterialTheme.typography.bodySmall)
                Text("AI 확인은 추적된 표시창의 축 정렬 경계 상자를 촬영하므로 기울면 주변 영역도 포함됩니다.",
                    style = MaterialTheme.typography.bodySmall)
                Button(onClick = { coordinator.identify(photoConsent) }, enabled = !state.busy && photoConsent) {
                    Text("사진 1장 · 실제 식별")
                }
                state.candidates.forEach { candidate ->
                    Card {
                        Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("${if (candidate.demo) "DEMO" else "등록 후보"} · ${candidate.model}")
                            Text("검색 점수 ${candidate.score} (확률 아님)")
                            Text("리모컨 외형만으로 정확한 본체 모델이 증명되지 않습니다.")
                            candidate.guideIds.forEach { id ->
                                Button(onClick = { coordinator.selectGuide(id, candidate.model) },
                                    enabled = !state.busy && state.pending == null) {
                                    Text("사용자 확인 · ${state.catalog.first { it.id == id }.title}")
                                }
                            }
                        }
                    }
                }
                OutlinedButton(onClick = { showCatalog = !showCatalog }) { Text("게시된 가이드 수동 선택") }
                if (showCatalog) {
                    if (state.catalog.isEmpty()) Text("게시된 승인 가이드가 없습니다.")
                    state.catalog.forEach { guide ->
                        OutlinedButton(onClick = { coordinator.selectGuide(guide.id, "등록 가이드 수동 선택: ${guide.title}") },
                            enabled = !state.busy && state.pending == null) {
                            Text("${if (guide.demo) "DEMO" else "등록 자산"} · ${guide.title} · 선택 확인")
                        }
                    }
                }
            }
            state.session?.let { session ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(state.guide?.title.orEmpty(), style = MaterialTheme.typography.titleMedium)
                        Text(state.confirmedLabel)
                        Text(if (session.finished) "서버 승인 · 완료" else "${session.stepIndex + 1}/${state.guide?.steps?.size} · ${state.step?.id}")
                        Text(state.step?.instruction ?: "서버의 마지막 단계가 완료되었습니다.")
                        Text("서버 확인 출처: ${session.lastSource ?: "아직 없음"}")
                    }
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Button(onClick = coordinator::manual,
                        enabled = !state.busy && !session.finished && state.pending == null) { Text("수동 확인 · 서버 승인") }
                    Button(onClick = { coordinator.verify(photoConsent) },
                        enabled = !state.busy && !session.finished && state.pending == null &&
                            photoConsent && state.overlay.fullTracking) { Text("AI 확인 · 표시창 1장") }
                    OutlinedButton(onClick = coordinator::refreshSession, enabled = !state.busy) { Text("서버 단계 새로고침") }
                }
                if (state.pending != null) {
                    Text("미확인 이벤트를 저장했습니다. 같은 UUID로 재시도하며 단계를 건너뛰지 않습니다.")
                    Button(onClick = coordinator::retryPending, enabled = !state.busy) { Text("동일 이벤트 재시도") }
                    OutlinedButton(onClick = coordinator::reconcilePending, enabled = !state.busy) {
                        Text("재시도 대신 · 서버 조회 후 미확인 요청 정리")
                    }
                }
                FlowRow {
                    Checkbox(state.automatic, coordinator::setAutomatic,
                        enabled = !state.busy && !session.finished)
                    Text("안정된 OCR 텍스트 자동 전송 (${state.samples}/3)", Modifier.padding(top = 12.dp))
                }
                Text(state.ocrStatus, style = MaterialTheme.typography.bodySmall)
                if (state.ocrText.isNotEmpty()) Text("현재 로컬 OCR: ${state.ocrText.take(100)}")
                Text("OCR은 표시 상태만 확인합니다. fail/unsure 또는 네트워크 오류는 완료가 아닙니다.",
                    style = MaterialTheme.typography.bodySmall)
            }
            FlowRow {
                Checkbox(voice, { voice = it })
                Text("한국어 음성", Modifier.padding(top = 12.dp))
                OutlinedButton(onClick = { speech.speak(state.step?.instruction ?: "현재 단계가 없습니다.") },
                    enabled = voiceReady) { Text("다시 읽기") }
            }
            Text(voiceStatus, style = MaterialTheme.typography.bodySmall)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedButton(onClick = { coordinator.pause(); cameraGeneration++ }) { Text("카메라 재시도") }
                OutlinedButton(onClick = { coordinator.pause(); leave() }) { Text("모드 선택으로") }
            }
        }
    })
}
