package kr.demo.visualguide

import android.graphics.BitmapFactory
import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kr.demo.guide.CaptureScope
import kr.demo.guide.OcrEvidence
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.util.UUID
import java.util.concurrent.atomic.AtomicReference

data class CloudUiState(
    val savedOrigin: String = "", val registered: Boolean = false, val connected: Boolean = false,
    val busy: Boolean = false, val message: String = "HTTPS API와 단말 페어링을 설정하세요.",
    val error: String? = null, val catalog: List<CloudGuide> = emptyList(),
    val guide: CloudGuide? = null, val session: CloudSession? = null, val target: DemoAssets? = null,
    val candidates: List<CloudCandidate> = emptyList(), val confirmedLabel: String = "",
    val pending: CloudEvent? = null, val overlay: OverlayFrame = OverlayFrame(),
    val automatic: Boolean = false, val ocrText: String = "", val samples: Int = 0,
    val cameraStatus: String = "AR 카메라 준비 중", val ocrStatus: String = "OCR 자동 전송 꺼짐",
    val category: String = "aircon", val kind: String = "remote",
) {
    val step: CloudStep? get() = session?.let { guide?.steps?.getOrNull(it.stepIndex) }
}

/** Main-thread coordinator. Network/Keystore work runs on IO; server session is the only progress authority. */
class CloudCoordinator(private val store: SecureDeviceStore, private val scope: CoroutineScope) {
    var state by mutableStateOf(CloudUiState())
        private set
    val cameraRequest = AtomicReference<CaptureRequest?>(null)
    val snapshots = CameraSnapshotChannel()
    private var registration: DeviceRegistration? = null
    private var api: CloudApiClient? = null
    private var version = 0L
    private var epoch = 0L
    private var operation: Job? = null
    private val evidence = CloudEvidenceGate()
    val captureScope: CaptureScope? get() = state.step?.let { CaptureScope(it.id, epoch) }

    fun initialize() = run("암호화된 단말 등록 확인 중") {
        registration = withContext(Dispatchers.IO) { store.load() }
        state = state.copy(registered = registration != null,
            savedOrigin = registration?.origin.orEmpty(), pending = registration?.pending,
            message = if (registration == null) "단말 페어링이 필요합니다." else "저장된 단말로 연결하여 세션을 복원할 수 있습니다.")
    }

    fun pairAndConnect(url: String, code: String) {
        if (state.busy) return
        invalidate()
        run("일회용 코드로 HTTPS 페어링 중") {
            val endpoint = ApiEndpoint.parse(url)
            clearChangedOrigin(endpoint, always = true)
            val paired = CloudApiClient(endpoint).pair(code.trim())
            persist(paired)
            api = CloudApiClient(endpoint, paired.token)
            state = state.copy(registered = true, savedOrigin = endpoint.origin, pending = null,
                guide = null, session = null, target = null, overlay = OverlayFrame(), confirmedLabel = "")
            bumpEvidence()
            connectCatalog()
        }
    }
    fun connectSaved(url: String) {
        if (state.busy) return
        invalidate()
        state = state.copy(connected = false, catalog = emptyList(), candidates = emptyList(),
            guide = null, session = null, target = null, overlay = OverlayFrame(), confirmedLabel = "")
        updateCapture()
        run("저장된 단말로 HTTPS 연결 중") {
            val endpoint = ApiEndpoint.parse(url)
            clearChangedOrigin(endpoint)
            val saved = requireNotNull(registration) { "API 원점 변경으로 이전 토큰/세션을 삭제했습니다. 다시 페어링하세요." }
            require(endpoint.origin == saved.origin) { "이 토큰은 다른 API 원점에 속합니다. 새 원점에서는 다시 페어링하세요." }
            require(saved.expiresAtMs > System.currentTimeMillis()) { "단말 토큰이 만료되었습니다. 새 코드로 페어링하세요." }
            api = CloudApiClient(endpoint, saved.token)
            connectCatalog()
        }
    }
    private suspend fun connectCatalog() {
        val catalog = currentApi().catalog()
        state = state.copy(connected = true, catalog = catalog, candidates = emptyList(),
            message = "인증된 등록 카탈로그를 불러왔습니다. 사진 식별 또는 가이드 수동 선택을 사용하세요.")
        val sessionId = registration?.sessionId
        if (sessionId != null) loadSession(currentApi().session(sessionId), null)
    }

    fun selectGuide(id: String, label: String) {
        if (state.busy) return
        if (state.catalog.none { it.id == id }) {
            state = state.copy(error = "현재 승인 카탈로그에 없는 가이드입니다. 새로 연결한 뒤 다시 선택하세요.")
            return
        }
        invalidate()
        state = state.copy(guide = null, session = null, target = null, overlay = OverlayFrame())
        updateCapture()
        run("승인된 가이드/지도/참조 이미지와 새 서버 세션을 불러오는 중") {
            val guide = approvedGuide(id)
            val target = fetchTarget(guide)
            val session = currentApi().start(guide.id)
            session.validate(guide)
            persist(requireNotNull(registration).copy(sessionId = session.id, pending = null))
            state = state.copy(guide = guide, target = target, session = session, pending = null,
                confirmedLabel = label, candidates = emptyList(),
                message = "사용자 선택이 확인되었습니다. 진행은 서버 승인 후 반영됩니다.")
            bumpEvidence()
        }
    }
    fun identify(consent: Boolean) {
        if (!consent) { state = state.copy(error = "버튼별 사진 1장 전송 동의가 필요합니다."); return }
        if (state.busy) return
        val category = state.category
        val kind = state.kind
        val text = state.ocrText
        state = state.copy(candidates = emptyList())
        run("ARCore 카메라에서 사진 1장 촬영 후 실제 식별 요청 중") {
            val photo = snapshots.capture(CaptureArea.SCENE)
            val result = currentApi().identify(category, kind, photo, text, state.catalog)
            state = state.copy(candidates = result.candidates, message = if (result.status == "unknown")
                "미등록/불확실 대상입니다. 임의 모델이나 가이드로 대체하지 않습니다."
                else "파이프라인 ${result.provider} · 사용자가 모델/DEMO 후보를 확인해야 합니다. 검색 점수는 확률이 아닙니다.")
        }
    }
    fun verify(consent: Boolean) {
        if (!consent) { state = state.copy(error = "버튼별 사진 1장 전송 동의가 필요합니다."); return }
        if (state.busy || state.pending != null) return
        val session = state.session ?: return
        val step = state.step ?: return
        val capture = captureScope ?: return
        run("현재 FULL_TRACKING 표시창을 촬영하여 AI 확인 중") {
            requireEvidence(capture)
            val photo = snapshots.capture(CaptureArea.DISPLAY, capture)
            requireEvidence(capture)
            val result = currentApi().verify(session.id, step.id, photo)
            requireEvidence(capture)
            state = state.copy(message = "AI ${result.status} · 배포 ${result.deployment}: ${result.reason}")
            if (result.status == "pass") {
                submitNew(CloudEvent(UUID.randomUUID().toString(), step.id, "vlm",
                    verificationId = result.proof), session.id)
            }
        }
    }
    fun manual() {
        if (state.busy || state.pending != null) return
        val session = state.session ?: return
        val step = state.step ?: return
        run("현재 단계 수동 확인을 서버에 전송 중") {
            submitNew(CloudEvent(UUID.randomUUID().toString(), step.id, "manual"), session.id)
        }
    }
    fun retryPending() {
        if (state.busy) return
        val event = state.pending ?: return
        val sessionId = registration?.sessionId ?: return
        run("저장된 동일 이벤트 UUID로 재시도 중") { submitPending(event, sessionId) }
    }
    fun refreshSession() {
        if (state.busy) return
        val id = registration?.sessionId ?: return
        run("서버의 현재 세션 새로고침 중") { loadSession(currentApi().session(id), state.confirmedLabel) }
    }
    fun reconcilePending() {
        if (state.busy || state.pending == null) return
        val id = registration?.sessionId ?: return
        run("서버 상태를 확인한 뒤 미확인 이벤트를 정리하는 중") {
            val current = currentApi().session(id)
            current.validate(requireNotNull(state.guide))
            require(current.id == id && current.stepIndex >= (state.session?.stepIndex ?: 0))
            persist(requireNotNull(registration).copy(pending = null))
            state = state.copy(session = current, pending = null,
                message = "서버 현재 단계를 반영했습니다. 아직 미완료라면 사진을 다시 확인하세요.")
            bumpEvidence()
        }
    }
    private suspend fun submitNew(event: CloudEvent, sessionId: String) {
        val saved = requireNotNull(registration)
        require(saved.sessionId == sessionId && state.session?.currentStepId == event.stepId)
        persist(saved.copy(pending = event))
        state = state.copy(pending = event)
        submitPending(event, sessionId)
    }
    private suspend fun submitPending(event: CloudEvent, sessionId: String) {
        val guide = requireNotNull(state.guide)
        val index = guide.steps.indexOfFirst { it.id == event.stepId }
        require(index >= 0) { "저장된 이벤트가 현재 가이드에 없습니다." }
        val accepted = currentApi().advance(sessionId, event)
        accepted.validate(guide)
        require(accepted.id == sessionId && accepted.stepIndex == index + 1 &&
            accepted.lastSource == event.source) {
            "이벤트 승인 응답이 요청 단계와 일치하지 않습니다."
        }
        // A replay returns the original response; read the live session to avoid rolling progress back.
        val current = currentApi().session(sessionId)
        current.validate(guide)
        require(current.id == sessionId && current.stepIndex >= accepted.stepIndex)
        persist(requireNotNull(registration).copy(pending = null))
        state = state.copy(session = current, pending = null,
            message = "서버 승인 완료 · 출처 ${event.source}", error = null)
        bumpEvidence()
    }
    private suspend fun approvedGuide(id: String): CloudGuide {
        val published = state.catalog.firstOrNull { it.id == id }
            ?: throw IllegalArgumentException("승인된 카탈로그에 없는 가이드입니다.")
        return currentApi().guide(id).also {
            require(it.id == published.id && it.targetId == published.targetId && it.demo == published.demo)
        }
    }
    private suspend fun fetchTarget(guide: CloudGuide): DemoAssets {
        val model = currentApi().model(guide.targetId)
        model.validate(guide)
        val bytes = currentApi().reference(model)
        withContext(Dispatchers.Default) {
            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
            require(options.outWidth == model.imageWidth && options.outHeight == model.imageHeight) {
                "참조 이미지 크기가 등록 지도와 일치하지 않습니다."
            }
        }
        return DemoAssets(model.id, "", model.physicalWidth, model.display, model.buttons, bytes,
            guide.demo, if (guide.demo) "등록 DEMO · ${guide.title}" else "등록 대상 · ${guide.title}")
    }
    private suspend fun loadSession(session: CloudSession, label: String?) {
        val guide = approvedGuide(session.guideId)
        session.validate(guide)
        require(session.id == registration?.sessionId)
        val old = state.session
        require(old == null || old.id != session.id || session.stepIndex >= old.stepIndex)
        val target = fetchTarget(guide)
        state = state.copy(session = session, guide = guide, target = target,
            pending = registration?.pending, overlay = OverlayFrame(),
            confirmedLabel = label ?: "저장된 사용자 선택 복원",
            message = "서버 세션 복원 완료. 단계는 서버 응답에서만 반영합니다.")
        bumpEvidence()
    }
    fun onFrame(frame: OverlayFrame) {
        if (state.overlay.fullTracking != frame.fullTracking) {
            state = state.copy(overlay = frame,
                ocrStatus = if (frame.fullTracking) "현재 타깃 OCR 대기 중" else "추적 없음: 자동 OCR 확인 중지")
            bumpEvidence()
        } else state = state.copy(overlay = frame)
    }
    fun onOcr(value: OcrEvidence) {
        if (value.scope != captureScope) return
        state = state.copy(ocrText = value.text.take(2048))
        val step = state.step ?: return
        val session = state.session ?: return
        val capture = captureScope ?: return
        if (!state.automatic || state.busy || state.pending != null) return
        val stable = evidence.observe(value, capture, step.expected, state.overlay.fullTracking, SystemClock.elapsedRealtime())
        state = state.copy(samples = evidence.samples)
        if (stable) run("안정된 OCR 텍스트를 서버에 확인 요청 중") {
            requireEvidence(capture)
            submitNew(CloudEvent(UUID.randomUUID().toString(), step.id, "ocr", value.text), session.id)
        }
    }
    fun setAutomatic(value: Boolean) {
        state = state.copy(automatic = value,
            ocrStatus = if (value) "현재 FULL_TRACKING에서 3개 이상 안정 프레임의 텍스트만 전송합니다." else "자동 OCR 텍스트 전송 꺼짐")
        bumpEvidence()
    }
    fun setCategory(value: String) {
        if (!state.busy && value in listOf("aircon", "tv", "airdresser")) {
            state = state.copy(category = value, candidates = emptyList())
        }
    }
    fun setKind(value: String) {
        if (!state.busy && value in listOf("body", "remote", "screen")) {
            state = state.copy(kind = value, candidates = emptyList())
        }
    }
    fun cameraStatus(value: String) { state = state.copy(cameraStatus = value) }
    fun ocrStatus(value: String) { state = state.copy(ocrStatus = value) }
    fun pause() {
        invalidate()
        state = state.copy(overlay = OverlayFrame(), busy = false,
            message = "카메라/작업 중지됨. 미확인 진행은 동일 이벤트 ID로 재시도하세요.")
    }
    fun forget() {
        invalidate()
        run("암호화된 단말 등록 삭제 중") {
            clearStore()
            registration = null
            api = null
            state = CloudUiState(message = "단말 등록을 삭제했습니다. 오프라인 모드로 자동 전환하지 않습니다.")
            updateCapture()
        }
    }
    fun forgetSession() {
        if (state.busy) return
        invalidate()
        run("저장된 세션 복원 정보를 정리하는 중") {
            persist(requireNotNull(registration).copy(sessionId = null, pending = null))
            state = state.copy(guide = null, session = null, target = null, pending = null,
                overlay = OverlayFrame(), candidates = emptyList(), confirmedLabel = "",
                message = "세션 복원 정보를 포기했습니다. 기존 서버 기록은 삭제되지 않습니다. 새 가이드를 직접 선택하세요.")
            bumpEvidence()
        }
    }
    private fun requireEvidence(expected: CaptureScope) {
        require(expected == captureScope && state.overlay.fullTracking) { "이전 단계/추적이 끊긴 증거를 취소했습니다." }
    }
    private fun currentApi(): CloudApiClient {
        require(requireNotNull(registration).expiresAtMs > System.currentTimeMillis()) { "단말 토큰 만료. 다시 페어링하세요." }
        return requireNotNull(api) { "먼저 HTTPS 단말 연결을 완료하세요." }
    }
    private suspend fun persist(value: DeviceRegistration) {
        withContext(Dispatchers.IO) {
            val context = currentCoroutineContext()
            store.save(value) { context.ensureActive() }
        }
        registration = value
    }
    private suspend fun clearStore() = withContext(Dispatchers.IO) {
        val context = currentCoroutineContext()
        store.clear { context.ensureActive() }
    }
    private suspend fun clearChangedOrigin(endpoint: ApiEndpoint, always: Boolean = false) {
        if (always || registration != null && registration?.origin != endpoint.origin) {
            clearStore()
            registration = null
            api = null
            state = CloudUiState(busy = true, savedOrigin = endpoint.origin,
                message = "페어링/원점 변경: 이전 토큰/세션을 요청 전에 삭제했습니다.")
            bumpEvidence()
        }
    }
    private fun bumpEvidence() {
        epoch++
        evidence.reset()
        state = state.copy(samples = 0, ocrText = "")
        updateCapture()
    }
    private fun updateCapture() {
        cameraRequest.set(state.step?.let { CaptureRequest(requireNotNull(captureScope), it.buttonId, state.automatic) })
    }
    private fun invalidate() {
        version++
        operation?.cancel()
        snapshots.cancel()
        bumpEvidence()
    }
    private fun run(message: String, block: suspend () -> Unit) {
        if (state.busy) return
        val selected = version
        state = state.copy(busy = true, message = message, error = null)
        operation = scope.launch {
            try {
                block()
            } catch (_: TimeoutCancellationException) {
                if (version == selected) state = state.copy(error = "3.5초 안에 ARCore 사진을 얻지 못했습니다. 카메라 권한/추적 상태를 확인하세요.")
            } catch (_: CancellationException) {
                // Selection/lifecycle changes invalidate callbacks rather than completing a different step.
            } catch (error: Exception) {
                if (version == selected && error is DeviceRegistrationUnreadable) {
                    registration = null
                    api = null
                    state = CloudUiState(busy = true, error = error.message,
                        message = "기기 복원/키 오류: 다시 페어링이 필요합니다. 인증된 상태가 아닙니다.")
                    updateCapture()
                } else if (version == selected) state = state.copy(error = when (error) {
                    is CloudApiException, is IllegalArgumentException, is IllegalStateException ->
                        error.message?.take(300) ?: "요청을 완료하지 못했습니다."
                    else -> "연결/안전 저장소 오류: ${error.javaClass.simpleName}. 성공으로 처리하지 않았습니다."
                })
            } finally {
                if (version == selected) state = state.copy(busy = false)
            }
        }
    }
}
