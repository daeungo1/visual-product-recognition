package kr.demo.visualguide

import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import java.util.concurrent.atomic.AtomicReference

@Composable
internal fun TroubleshootingDemoScreen(activity: ComponentActivity, leave: () -> Unit) {
    val result = remember { runCatching { DemoScenarioCatalog.load(activity) } }
    val catalog = result.getOrNull()
    if (catalog == null) {
        Column(Modifier.fillMaxSize().padding(20.dp)) {
            Text("합성 제품 카탈로그 오류: ${result.exceptionOrNull()?.message}",
                color = MaterialTheme.colorScheme.error)
            OutlinedButton(onClick = leave) { Text("모드 선택으로") }
        }
        return
    }
    var selected by remember { mutableStateOf<DemoScenario?>(null) }
    var running by remember { mutableStateOf(false) }
    var selectionSource by remember { mutableStateOf("") }
    val scenario = selected
    BackHandler(scenario != null) {
        if (running) running = false else selected = null
    }
    if (running && scenario != null) {
        key(scenario.id) { GuideScreen(activity, scenario) { running = false } }
        return
    }
    if (scenario != null) {
        Column(Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("${scenario.product} · 증상 선택", style = MaterialTheme.typography.headlineSmall)
            Text("제품 선택 방식: $selectionSource")
            Text("DEMO · 실제 삼성 제품의 모델·고장을 식별한 결과가 아닙니다.",
                color = MaterialTheme.colorScheme.error)
            Text(scenario.issue, style = MaterialTheme.typography.titleLarge)
            Text(scenario.summary)
            Text("PC에서 같은 제품 타깃을 선택하세요. 등록 타깃이 현재 FULL_TRACKING일 때만 안내가 표시됩니다.")
            Text("PC 타깃: https://daeungo1.github.io/visual-product-recognition/")
            Button(onClick = { running = true }) { Text("이 증상 · Overlay 안내 시작") }
            OutlinedButton(onClick = { selected = null }) { Text("다른 제품 비추기") }
            Text("실제 제품은 모델명·공식 절차·검수 패널이 필요합니다. 발열·누수·연기 등 위험 징후가 있으면 실습을 중단하고 공식 지원을 이용하세요.")
        }
        return
    }
    var frame by remember { mutableStateOf(OverlayFrame()) }
    var cameraStatus by remember { mutableStateOf("카메라 준비 중") }
    var generation by remember { mutableIntStateOf(0) }
    var manual by remember { mutableStateOf(false) }
    val request = remember { AtomicReference<CaptureRequest?>(null) }
    val targets = remember(catalog) { catalog.map { it.assets } }
    val detected = if (frame.fullTracking) catalog.singleOrNull { it.assets.targetId == frame.targetId } else null
    AdaptiveGuideLayout(camera = { modifier ->
        Column(modifier.background(Color.Black)) {
            Text("카메라 → 제품 확인 → 증상 → Overlay", color = Color.White, modifier = Modifier.padding(8.dp))
            Box(Modifier.weight(1f)) {
                CameraPermissionHost(activity, null, request, generation, { frame = it }, {},
                    { cameraStatus = it }, {}, discoveryTargets = targets)
            }
        }
    }, controls = { modifier ->
        Column(modifier.verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("제품 이슈 해결 · 합성 DEMO", style = MaterialTheme.typography.titleLarge)
            Text("PC의 합성 에어컨·세탁기·냉장고·모니터 중 하나를 비추세요. 삼성 실제품·일반 사물은 등록되어 있지 않습니다.")
            Text(cameraStatus)
            Text(frame.message)
            Text(detected?.let { "감지 후보: 합성 ${it.product}" } ?: "미등록 또는 추적 불확실: 제품 확인 필요")
            Button(onClick = {
                detected?.let { selected = it; selectionSource = "카메라의 등록 합성 타깃 · 사용자 확인" }
            }, enabled = detected != null) { Text("이 제품 확인 · 증상 보기") }
            OutlinedButton(onClick = { manual = !manual }) { Text("수동 제품 선택 (인식 성공 아님)") }
            if (manual) catalog.forEach { item ->
                OutlinedButton(onClick = { selected = item; selectionSource = "사용자 수동 선택 · 인식 성공 아님" }) {
                    Text("합성 ${item.product} · ${item.issue}")
                }
            }
            OutlinedButton(onClick = { frame = OverlayFrame(); generation++ }) { Text("카메라 재시도") }
            OutlinedButton(onClick = leave) { Text("모드 선택으로") }
        }
    })
}
