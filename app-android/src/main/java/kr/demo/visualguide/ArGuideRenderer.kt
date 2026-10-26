package kr.demo.visualguide

import android.graphics.Bitmap
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.opengl.Matrix
import android.os.SystemClock
import com.google.ar.core.AugmentedImage
import com.google.ar.core.Coordinates2d
import com.google.ar.core.Frame
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import com.google.ar.core.exceptions.NotYetAvailableException
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions
import kr.demo.guide.CaptureScope
import kr.demo.guide.NormalizedRect
import kr.demo.guide.OcrEvidence
import kr.demo.guide.ScreenPoint
import kr.demo.guide.imagePoint
import kr.demo.guide.project
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.ceil
import kotlin.math.floor

data class CaptureRequest(val scope: CaptureScope, val buttonId: String, val automatic: Boolean)
data class OverlayFrame(
    val fullTracking: Boolean = false,
    val polygon: List<ScreenPoint> = emptyList(),
    val scope: CaptureScope? = null,
    val message: String = "등록된 DEMO 타깃 전체를 비추세요.",
    val targetId: String? = null,
)

internal class ArGuideRenderer(
    private val assets: DemoAssets?,
    private val request: AtomicReference<CaptureRequest?>,
    private val rotation: () -> Int,
    private val onFrame: (OverlayFrame) -> Unit,
    private val onOcr: (OcrEvidence) -> Unit,
    private val onOcrStatus: (String) -> Unit,
    private val onFailure: (String) -> Unit,
    private val snapshots: CameraSnapshotChannel? = null,
    private val discoveryTargets: List<DemoAssets> = emptyList(),
) : GLSurfaceView.Renderer {
    @Volatile var session: Session? = null
    @Volatile var sensorOrientation = 90
    val fullTracking = AtomicBoolean(false)
    private val disposed = AtomicBoolean(false)
    private val busy = AtomicBoolean(false)
    private val recognizer = TextRecognition.getClient(KoreanTextRecognizerOptions.Builder().build())
    private val background = CameraBackground()
    private var width = 1
    private var height = 1
    private var lastOcrMs = 0L
    private var lastImageTimestamp = 0L
    private var faulted = false

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        try {
            background.create()
            faulted = false
        } catch (error: Exception) {
            fail("카메라 화면 초기화 실패: ${error.message}")
        }
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        this.width = width
        this.height = height
        GLES20.glViewport(0, 0, width, height)
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClearColor(0.05f, 0.05f, 0.05f, 1f)
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
        val active = session ?: return
        if (disposed.get() || faulted) return
        try {
            active.setDisplayGeometry(rotation(), width, height)
            active.setCameraTextureName(background.textureId)
            val frame = active.update()
            background.draw(frame)
            val tracked = active.getAllTrackables(AugmentedImage::class.java)
                .filter {
                    it.trackingState == TrackingState.TRACKING &&
                        it.trackingMethod == AugmentedImage.TrackingMethod.FULL_TRACKING
                }
            if (assets == null && discoveryTargets.isNotEmpty()) {
                val known = discoveryTargets.map { it.targetId }.toSet()
                val detected = uniqueTrackedTarget(frame.camera.trackingState == TrackingState.TRACKING,
                    tracked.map { it.name }.filter { it in known })
                fullTracking.set(detected != null)
                onFrame(OverlayFrame(fullTracking = detected != null, targetId = detected,
                    message = if (detected == null) "합성 제품 타깃 하나를 전체가 보이도록 비추세요. 미등록 실제품은 선택하지 않습니다."
                    else "등록된 합성 제품 감지. 제품과 증상을 확인한 뒤 안내를 시작하세요."))
                return
            }
            val image = tracked.firstOrNull { it.name == assets?.targetId }
            val full = frame.camera.trackingState == TrackingState.TRACKING && image != null
            val matrix = image?.let { imageToClip(frame, it) }
            val display = if (image != null && matrix != null && assets != null)
                projectRect(assets.display, image, matrix) else emptyList()
            takeSnapshot(frame, full, display)
            if (!full || matrix == null || assets == null) {
                fullTracking.set(false)
                onFrame(OverlayFrame(message = if (assets == null) "대상 선택 전: 사진 식별만 가능합니다."
                    else "타깃 미추적: 하이라이트와 OCR을 숨겼습니다."))
                return
            }
            fullTracking.set(true)
            val capture = request.get()
            val button = capture?.let { assets.buttons[it.buttonId] }
            val polygon = button?.let { projectRect(it, image, matrix) }.orEmpty()
            onFrame(OverlayFrame(
                true, polygon, capture?.scope,
                "${assets.label} · FULL_TRACKING",
            ))
            if (capture?.automatic == true) {
                if (display.size == 4) maybeRecognize(frame, display, capture.scope)
            }
        } catch (error: Exception) {
            fail("AR 카메라 오류: ${error.javaClass.simpleName}. 권한/카메라 사용 상태를 확인하세요.")
        }
    }

    fun pauseTracking() {
        fullTracking.set(false)
        snapshots?.cancel()
        onFrame(OverlayFrame(message = "카메라 일시 중지: 표시를 숨겼습니다."))
    }

    fun close() {
        disposed.set(true)
        fullTracking.set(false)
        snapshots?.cancel()
        recognizer.close()
    }

    private fun fail(message: String) {
        faulted = true
        fullTracking.set(false)
        snapshots?.cancel()
        onFrame(OverlayFrame(message = message))
        onFailure(message)
    }

    private fun takeSnapshot(frame: Frame, full: Boolean, display: List<ScreenPoint>) {
        val channel = snapshots ?: return
        val pending = channel.peek() ?: return
        if (frame.camera.trackingState != TrackingState.TRACKING) {
            channel.fail(pending, "카메라가 현재 추적 중이 아닙니다.")
            return
        }
        if (pending.area == CaptureArea.DISPLAY &&
            (!full || display.size != 4 || pending.scope != request.get()?.scope)) {
            channel.fail(pending, "현재 단계의 등록 타깃을 FULL_TRACKING으로 비추세요.")
            return
        }
        try {
            val raw = frame.acquireCameraImage().use { image ->
                val crop = if (pending.area == CaptureArea.SCENE) PixelRect(0, 0, image.width, image.height)
                else {
                    val input = floatBuffer(display.flatMap { listOf(it.x, it.y) }.toFloatArray())
                    val output = floatBuffer(FloatArray(8))
                    frame.transformCoordinates2d(Coordinates2d.VIEW, input, Coordinates2d.IMAGE_PIXELS, output)
                    val points = FloatArray(8)
                    output.rewind()
                    output.get(points)
                    val xs = listOf(points[0], points[2], points[4], points[6])
                    val ys = listOf(points[1], points[3], points[5], points[7])
                    require(points.all { it.isFinite() } && xs.all { it >= 0 && it < image.width } &&
                        ys.all { it >= 0 && it < image.height }) { "표시창 전체를 카메라 안에 넣으세요." }
                    PixelRect(floor(xs.min()).toInt(), floor(ys.min()).toInt(),
                        ceil(xs.max()).toInt().coerceAtMost(image.width),
                        ceil(ys.max()).toInt().coerceAtMost(image.height)).also {
                        require(it.right - it.left >= 24 && it.bottom - it.top >= 24) { "표시창을 더 크게 비추세요." }
                    }
                }
                RawSnapshot(CameraSnapshotChannel.copy(image), crop,
                    (sensorOrientation - rotation() * 90 + 360) % 360)
            }
            channel.complete(pending, raw)
        } catch (_: NotYetAvailableException) {
            // Retry a later ARCore frame within the bounded user-initiated capture request.
        } catch (_: Exception) { channel.fail(pending, "카메라 이미지/표시창을 촬영하지 못했습니다.") }
    }

    private fun imageToClip(frame: Frame, image: AugmentedImage): FloatArray {
        val projection = FloatArray(16)
        val view = FloatArray(16)
        val model = FloatArray(16)
        val viewProjection = FloatArray(16)
        val result = FloatArray(16)
        frame.camera.getProjectionMatrix(projection, 0, 0.05f, 100f)
        frame.camera.getViewMatrix(view, 0)
        image.centerPose.toMatrix(model, 0)
        Matrix.multiplyMM(viewProjection, 0, projection, 0, view, 0)
        Matrix.multiplyMM(result, 0, viewProjection, 0, model, 0)
        return result
    }

    private fun projectRect(rect: NormalizedRect, image: AugmentedImage, matrix: FloatArray): List<ScreenPoint> {
        val points = rect.corners().map { (u, v) ->
            project(imagePoint(u, v, image.extentX, image.extentZ), matrix, width, height)
                ?: return emptyList()
        }
        return points
    }

    private fun maybeRecognize(frame: Frame, display: List<ScreenPoint>, scope: CaptureScope) {
        val now = SystemClock.elapsedRealtime()
        if (now - lastOcrMs < 500 || !busy.compareAndSet(false, true)) return
        lastOcrMs = now
        var bitmap: Bitmap? = null
        try {
            bitmap = frame.acquireCameraImage().use { image ->
                if (image.timestamp <= lastImageTimestamp) return@use null
                lastImageTimestamp = image.timestamp
                val viewPoints = floatBuffer(display.flatMap { listOf(it.x, it.y) }.toFloatArray())
                val pixelPoints = floatBuffer(FloatArray(8))
                frame.transformCoordinates2d(
                    Coordinates2d.VIEW, viewPoints, Coordinates2d.IMAGE_PIXELS, pixelPoints,
                )
                val coords = FloatArray(8)
                pixelPoints.rewind()
                pixelPoints.get(coords)
                val xs = listOf(coords[0], coords[2], coords[4], coords[6])
                val ys = listOf(coords[1], coords[3], coords[5], coords[7])
                if (coords.any { !it.isFinite() } || xs.any { it < 0 || it >= image.width } ||
                    ys.any { it < 0 || it >= image.height }) return@use null
                val left = floor(xs.min()).toInt()
                val top = floor(ys.min()).toInt()
                val right = ceil(xs.max()).toInt().coerceAtMost(image.width)
                val bottom = ceil(ys.max()).toInt().coerceAtMost(image.height)
                val cropWidth = right - left
                val cropHeight = bottom - top
                if (cropWidth < 24 || cropHeight < 24 || cropWidth.toLong() * cropHeight > 1_000_000) {
                    return@use null
                }
                val plane = image.planes[0]
                val buffer = plane.buffer
                val base = buffer.position()
                val colors = IntArray(cropWidth * cropHeight)
                for (y in 0 until cropHeight) for (x in 0 until cropWidth) {
                    val value = buffer.get(base + (top + y) * plane.rowStride + (left + x) * plane.pixelStride)
                        .toInt() and 0xff
                    colors[y * cropWidth + x] = (0xff shl 24) or (value shl 16) or (value shl 8) or value
                }
                Bitmap.createBitmap(colors, cropWidth, cropHeight, Bitmap.Config.ARGB_8888)
            }
            val cropped = bitmap
            if (cropped == null) {
                busy.set(false)
                onOcrStatus("OCR 대기: 표시창 전체를 더 크게, 정면으로 비추세요.")
                return
            }
            val rotationDegrees = (sensorOrientation - rotation() * 90 + 360) % 360
            recognizer.process(InputImage.fromBitmap(cropped, rotationDegrees))
                .addOnSuccessListener { text ->
                    if (!disposed.get() && fullTracking.get()) {
                        onOcr(OcrEvidence(scope, now, text.text.take(2048)))
                        onOcrStatus("표시창 OCR: ${text.text.take(100).replace('\n', ' ')}")
                    }
                }
                .addOnFailureListener { error ->
                    if (!disposed.get()) onOcrStatus("OCR 실패: ${error.javaClass.simpleName}. 수동 확인을 사용하세요.")
                }
                .addOnCompleteListener {
                    cropped.recycle()
                    busy.set(false)
                }
        } catch (_: NotYetAvailableException) {
            bitmap?.recycle()
            busy.set(false)
            onOcrStatus("CPU 카메라 이미지 대기 중. 수동 확인은 가능합니다.")
        } catch (error: Exception) {
            bitmap?.recycle()
            busy.set(false)
            onOcrStatus("OCR 사용 불가: ${error.javaClass.simpleName}. 수동 확인을 사용하세요.")
        }
    }
}
