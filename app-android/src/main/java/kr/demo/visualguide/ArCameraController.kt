package kr.demo.visualguide

import android.app.Activity
import android.graphics.BitmapFactory
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.opengl.GLSurfaceView
import com.google.ar.core.ArCoreApk
import com.google.ar.core.AugmentedImageDatabase
import com.google.ar.core.Config
import com.google.ar.core.Session
import kr.demo.guide.OcrEvidence
import java.util.concurrent.atomic.AtomicReference

internal class ArCameraController(
    private val activity: Activity,
    private val assets: DemoAssets?,
    request: AtomicReference<CaptureRequest?>,
    private val onFrame: (OverlayFrame) -> Unit,
    onOcr: (OcrEvidence) -> Unit,
    onOcrStatus: (String) -> Unit,
    private val onStatus: (String) -> Unit,
    snapshots: CameraSnapshotChannel? = null,
    private val discoveryTargets: List<DemoAssets> = emptyList(),
) {
    @Suppress("DEPRECATION")
    private fun rotation(): Int = activity.windowManager.defaultDisplay.rotation

    private val renderer = ArGuideRenderer(
        assets, request, ::rotation, ::publishFrame,
        { evidence -> activity.runOnUiThread { if (!closed && running) onOcr(evidence) } },
        { message -> activity.runOnUiThread { if (!closed && running) onOcrStatus(message) } },
        { message -> activity.runOnUiThread { if (!closed) onStatus(message) } }, snapshots, discoveryTargets,
    )
    val surface = GLSurfaceView(activity).apply {
        setEGLContextClientVersion(2)
        preserveEGLContextOnPause = true
        setRenderer(renderer)
        renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
    }
    private var session: Session? = null
    private var running = false
    private var installRequested = false
    private var closed = false

    private fun publishFrame(frame: OverlayFrame) {
        activity.runOnUiThread {
            if (!closed) {
                onFrame(if (running) frame else OverlayFrame(message = "카메라 일시 중지: 표시를 숨겼습니다."))
            }
        }
    }

    fun resume() {
        if (closed || running) return
        try {
            val apk = ArCoreApk.getInstance()
            val availability = apk.checkAvailability(activity)
            if (availability.isTransient) {
                onStatus("ARCore 지원 확인 중입니다. 잠시 후 '카메라 재시도'를 누르세요.")
                return
            }
            if (!availability.isSupported) {
                onStatus("이 기기에서는 ARCore를 사용할 수 없습니다 ($availability). 수동 가이드만 가능합니다.")
                return
            }
            if (apk.requestInstall(activity, !installRequested) == ArCoreApk.InstallStatus.INSTALL_REQUESTED) {
                installRequested = true
                onStatus("Google Play AR 서비스 설치/업데이트가 필요합니다. 설치 후 앱으로 돌아오세요.")
                return
            }
            val active = session ?: createSession().also { session = it }
            active.resume()
            renderer.session = active
            surface.onResume()
            running = true
            onStatus(if (discoveryTargets.isNotEmpty() && assets == null) "AR 카메라 사용 중: 4종 합성 제품 탐지"
                else if (assets == null) "AR 카메라 사용 중. 등록 대상 선택 전입니다."
                else "AR 카메라 사용 중: ${assets.label}")
        } catch (error: Exception) {
            renderer.session = null
            session?.close()
            session = null
            renderer.pauseTracking()
            onStatus("ARCore/카메라 시작 실패: ${error.javaClass.simpleName}. 설치, 권한, 다른 카메라 앱을 확인하세요.")
        }
    }

    private fun createSession(): Session {
        val created = Session(activity)
        try {
            val database = AugmentedImageDatabase(created)
            val targets = assets?.let { listOf(it) } ?: discoveryTargets
            require(targets.map { it.targetId }.distinct().size == targets.size)
            for (target in targets) {
                val bitmap = target.referenceBytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
                    ?: if (target.referenceBytes == null) activity.assets.open(target.image).use {
                        BitmapFactory.decodeStream(it)
                    } else null
                requireNotNull(bitmap) { "등록된 참조 이미지를 읽을 수 없습니다." }
                try {
                    database.addImage(target.targetId, bitmap, target.physicalWidth)
                } finally { bitmap.recycle() }
            }
            val config = Config(created).apply {
                augmentedImageDatabase = database
                focusMode = Config.FocusMode.AUTO
                planeFindingMode = Config.PlaneFindingMode.DISABLED
                updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
            }
            created.configure(config)
            val manager = activity.getSystemService(CameraManager::class.java)
            renderer.sensorOrientation = manager.getCameraCharacteristics(created.cameraConfig.cameraId)
                .get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 90
            return created
        } catch (error: Exception) {
            created.close()
            throw error
        }
    }

    fun pause() {
        renderer.session = null
        if (running) {
            running = false
            surface.onPause()
            session?.pause()
        }
        renderer.pauseTracking()
    }

    fun close() {
        if (closed) return
        pause()
        closed = true
        renderer.close()
        session?.close()
        session = null
    }
}
