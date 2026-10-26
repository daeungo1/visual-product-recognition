package kr.demo.visualguide

import android.os.Bundle
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import kr.demo.guide.AdvanceSource
import kr.demo.guide.DemoGuide
import kr.demo.guide.GuideEngine
import kr.demo.guide.OcrEvidence
import java.util.concurrent.atomic.AtomicReference

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize().safeDrawingPadding()) { DemoApp(this) }
            }
        }
    }
}

@Composable
private fun DemoApp(activity: ComponentActivity) {
    var mode by remember { mutableStateOf<String?>(null) }
    if (mode == null) {
        Column(Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("시각 가이드 · 모드 선택", style = MaterialTheme.typography.headlineMedium)
            Text("오프라인 DEMO와 HTTPS 연결 모드는 별개입니다. 연결 실패 시 자동으로 DEMO를 실행하지 않습니다.")
            Text("에어컨·세탁기·냉장고·모니터를 비추고 증상별 Overlay를 확인하는 합성 실습입니다.")
            Button(onClick = { mode = "troubleshooting" }) { Text("카메라로 제품 이슈 DEMO") }
            OutlinedButton(onClick = { mode = "photo" }) { Text("에어컨·모니터 실모델 사진 참조 DEMO") }
            OutlinedButton(onClick = { mode = "cloud" }) { Text("실제 HTTPS 클라우드 연결") }
            OutlinedButton(onClick = { mode = "offline" }) { Text("기존 리모컨 · 오프라인 DEMO") }
        }
        return
    }
    if (mode == "troubleshooting") {
        BackHandler { mode = null }
        TroubleshootingDemoScreen(activity) { mode = null }
        return
    }
    if (mode == "photo") {
        BackHandler { mode = null }
        PhotoDemoScreen(activity) { mode = null }
        return
    }
    if (mode == "cloud") {
        BackHandler { mode = null }
        CloudGuideScreen(activity) { mode = null }
        return
    }
    var page by remember { mutableIntStateOf(0) }
    var unsupported by remember { mutableStateOf(false) }
    BackHandler(page > 0) { page-- }
    when (page) {
        0 -> Column(
            Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("시각 가이드 DEMO", style = MaterialTheme.typography.headlineMedium)
            DemoNotice()
            Text("1. 카테고리 선택")
            Button(onClick = { page = 1 }) { Text("에어컨 · 합성 리모컨 실습") }
            OutlinedButton(onClick = { unsupported = true }) { Text("실제 삼성 제품") }
            if (unsupported) Text("지원 불가: 실제 모델 참조 이미지와 버튼 맵이 등록되지 않았습니다. 실제 기기에 DEMO 좌표를 적용하지 않습니다.")
            Text("이 오프라인 DEMO 모드에서는 서버에 연결하지 않습니다. 카메라 없이도 수동 단계 안내가 가능합니다.")
            OutlinedButton(onClick = { mode = null }) { Text("연결/오프라인 모드 선택") }
        }
        1 -> Column(
            Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("2. 가이드 선택", style = MaterialTheme.typography.headlineMedium)
            DemoNotice()
            Text(DemoGuide.guide.title)
            Text("다른 컴퓨터/태블릿에서 assets\\demo-target.html을 여세요. 전원 켜기 → 냉방 모드 → 24도 설정을 실습합니다.")
            Text("앱의 하이라이트는 등록 그림의 현재 버튼 위치를 나타냅니다. OCR은 화면 문자를 확인할 뿐, 물리 버튼을 눌렀다는 증거가 아닙니다.")
            Button(onClick = { page = 2 }) { Text("DEMO 시작") }
            OutlinedButton(onClick = { page = 0 }) { Text("카테고리로") }
        }
        else -> GuideScreen(activity) { page = 1 }
    }
}

@Composable
private fun DemoNotice() {
    Text(
        "DEMO · 원본 합성 그림 전용\n실제 삼성 제품/설명서/사진 미등록. 실제 제품 인식이 아닙니다.",
        color = MaterialTheme.colorScheme.error,
    )
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
internal fun GuideScreen(activity: ComponentActivity, scenario: DemoScenario? = null, leave: () -> Unit) {
    val guide = scenario?.guide ?: DemoGuide.guide
    val engine = remember(guide.id) { GuideEngine(guide) }
    val capture = remember { AtomicReference<CaptureRequest?>(null) }
    var revision by remember { mutableIntStateOf(0) }
    var automatic by remember { mutableStateOf(false) }
    var voice by remember { mutableStateOf(false) }
    var voiceReady by remember { mutableStateOf(false) }
    var voiceStatus by remember { mutableStateOf("한국어 음성 초기화 중") }
    var overlay by remember { mutableStateOf(OverlayFrame()) }
    var cameraStatus by remember { mutableStateOf("카메라 준비 중") }
    var ocrStatus by remember { mutableStateOf("자동 확인 꺼짐. 수동 확인을 사용할 수 있습니다.") }
    var cameraGeneration by remember { mutableIntStateOf(0) }
    val speech = remember {
        AndroidSpeech(activity) { message, ready ->
            activity.runOnUiThread { voiceStatus = message; voiceReady = ready }
        }
    }
    val assetsResult = remember(guide.id) { runCatching { scenario?.assets ?: DemoAssets.load(activity) } }

    fun refresh() {
        capture.set(engine.currentStep?.let { step ->
            CaptureRequest(engine.scope!!, step.buttonId, automatic)
        })
        revision++
    }
    fun clearTracking() {
        engine.setTracking(false)
        engine.invalidateEvidence()
        overlay = OverlayFrame()
        refresh()
    }

    val onFrame: (OverlayFrame) -> Unit = { frame ->
        activity.runOnUiThread {
            val previousScope = engine.scope
            engine.setTracking(frame.fullTracking)
            overlay = frame
            if (engine.scope != previousScope) refresh()
        }
    }
    val onOcr: (OcrEvidence) -> Unit = { evidence ->
        activity.runOnUiThread {
            if (automatic && engine.observe(evidence, SystemClock.elapsedRealtime())) refresh()
            else revision++
        }
    }
    val onCameraStatus: (String) -> Unit = { message ->
        activity.runOnUiThread { cameraStatus = message }
    }
    val onOcrStatus: (String) -> Unit = { message ->
        activity.runOnUiThread { ocrStatus = message }
    }

    LaunchedEffect(Unit) { refresh() }
    // revision makes the framework-free mutable reducer observable to Compose.
    val currentStep = remember(revision) { engine.currentStep }
    LaunchedEffect(currentStep?.id, voice, voiceReady) {
        if (voice && voiceReady) speech.speak(currentStep?.instruction ?: "데모 가이드를 완료했습니다.")
        else speech.stop()
    }
    DisposableEffect(Unit) {
        onDispose {
            capture.set(null)
            speech.close()
        }
    }
    AdaptiveGuideLayout(camera = { cameraModifier ->
        Column(cameraModifier.background(Color.Black)) {
            Text(
                "DEMO · 실제 삼성 자산 미등록",
                color = Color.White,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(6.dp),
            )
            Box(Modifier.fillMaxWidth().weight(1f)) {
                val assets = assetsResult.getOrNull()
                if (assets != null) {
                    CameraPermissionHost(
                        activity, assets, capture, cameraGeneration, onFrame, onOcr,
                        onCameraStatus, onOcrStatus,
                    )
                } else {
                    Text(
                        "DEMO 참조 파일 오류: ${assetsResult.exceptionOrNull()?.message}. 카메라 가이드는 사용 불가합니다.",
                        color = Color.White, modifier = Modifier.padding(16.dp),
                    )
                }
                val polygon = if (engine.highlightVisible && overlay.scope == engine.scope) overlay.polygon else emptyList()
                Canvas(Modifier.fillMaxSize()) {
                    if (polygon.size == 4) {
                        val path = Path().apply {
                            moveTo(polygon[0].x, polygon[0].y)
                            polygon.drop(1).forEach { lineTo(it.x, it.y) }
                            close()
                        }
                        drawPath(path, Color.Yellow.copy(alpha = 0.25f))
                        drawPath(path, Color.Yellow, style = Stroke(width = 4.dp.toPx()))
                        drawCircle(Color.Yellow, 5.dp.toPx(), Offset(polygon[0].x, polygon[0].y))
                    }
                }
                if (scenario != null && polygon.size == 4) {
                    Card(Modifier.align(Alignment.BottomCenter).padding(8.dp)) {
                        Column(Modifier.padding(10.dp)) {
                            Text("합성 ${scenario.product} · ${scenario.issue}",
                                style = MaterialTheme.typography.labelLarge)
                            Text(currentStep?.instruction.orEmpty(),
                                style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }, controls = { controlsModifier ->
        Column(
            controlsModifier.verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text("DEMO · ${guide.title}", style = MaterialTheme.typography.titleMedium)
            Text("실제 삼성 자산 미등록 · 오프라인", color = MaterialTheme.colorScheme.error)
            Text(cameraStatus, style = MaterialTheme.typography.bodySmall)
            Text(overlay.message, style = MaterialTheme.typography.bodySmall)
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text(
                        if (currentStep == null) "표시 상태 실습 완료" else "${engine.stepIndex + 1}/${guide.steps.size} · ${currentStep.id}",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(currentStep?.instruction ?: "합성 화면 실습을 완료했습니다. 실제 제품 동작은 확인하지 않았습니다.")
                    Text("확인 출처: " + when (engine.history.lastOrNull()?.source) {
                        AdvanceSource.MANUAL -> "사용자 수동 확인"
                        AdvanceSource.STABLE_OCR -> "표시창 OCR 시간 안정성"
                        null -> "아직 없음"
                    }, style = MaterialTheme.typography.bodySmall)
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedButton(onClick = { engine.previous(); refresh() }, enabled = engine.stepIndex > 0) { Text("이전") }
                Button(
                    onClick = { currentStep?.let { engine.advanceManual(it.id); refresh() } },
                    enabled = currentStep != null,
                ) { Text("확인 · 다음") }
                OutlinedButton(onClick = { engine.reset(); refresh() }) { Text("초기화") }
            }
            FlowRow {
                Checkbox(automatic, onCheckedChange = {
                    automatic = it
                    engine.invalidateEvidence()
                    ocrStatus = if (it) "자동 확인: FULL_TRACKING 중 표시창의 3개 이상 프레임, 0.8초 이상 안정성이 필요합니다." else "자동 확인 꺼짐"
                    refresh()
                })
                Text("표시창 OCR 자동 확인 (${engine.stableSamples}/3)", Modifier.padding(top = 12.dp))
            }
            Text(ocrStatus, style = MaterialTheme.typography.bodySmall)
            FlowRow {
                Checkbox(voice, onCheckedChange = { voice = it })
                Text("한국어 음성", Modifier.padding(top = 12.dp))
                OutlinedButton(
                    onClick = { speech.speak(currentStep?.instruction ?: "데모 완료") },
                    enabled = voiceReady,
                ) { Text("다시 읽기") }
            }
            Text(voiceStatus, style = MaterialTheme.typography.bodySmall)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { clearTracking(); cameraGeneration++ }) { Text("카메라 재시도") }
                OutlinedButton(onClick = { clearTracking(); leave() }) { Text("가이드 선택") }
            }
        }
    })
}

@Composable
internal fun AdaptiveGuideLayout(
    camera: @Composable (Modifier) -> Unit,
    controls: @Composable (Modifier) -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxSize().padding(12.dp)) {
        // Bound both slots before measuring content so controls cannot consume the camera viewport.
        if (maxHeight < 500.dp) {
            Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                camera(Modifier.weight(1f).fillMaxHeight())
                controls(Modifier.weight(1f).fillMaxHeight())
            }
        } else {
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                camera(Modifier.fillMaxWidth().weight(1f))
                controls(Modifier.fillMaxWidth().weight(1f))
            }
        }
    }
}
