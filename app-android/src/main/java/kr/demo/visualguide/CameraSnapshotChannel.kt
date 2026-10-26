package kr.demo.visualguide

import android.graphics.Bitmap
import android.graphics.ImageFormat
import android.media.Image
import android.os.SystemClock
import kr.demo.guide.CaptureScope
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicReference

enum class CaptureArea { SCENE, DISPLAY }
data class SnapshotRequest(
    val area: CaptureArea, val scope: CaptureScope?, val deadlineMs: Long,
    val result: CompletableDeferred<RawSnapshot>,
)
data class RawSnapshot(val frame: YuvFrame, val crop: PixelRect, val rotation: Int)

class CameraSnapshotChannel {
    private val pending = AtomicReference<SnapshotRequest?>(null)

    suspend fun capture(area: CaptureArea, scope: CaptureScope? = null): ByteArray {
        val request = SnapshotRequest(area, scope, SystemClock.elapsedRealtime() + 3500, CompletableDeferred())
        check(pending.compareAndSet(null, request)) { "이미 사진 촬영 요청을 처리 중입니다." }
        val raw = try { withTimeout(3500) { request.result.await() } }
        finally { pending.compareAndSet(request, null) }
        return withContext(Dispatchers.Default) {
            val pixels = Yuv420Converter.rotate(Yuv420Converter.convert(raw.frame, raw.crop), raw.rotation)
            val bitmap = Bitmap.createBitmap(pixels.pixels, pixels.width, pixels.height, Bitmap.Config.ARGB_8888)
            try {
                val output = ByteArrayOutputStream()
                check(bitmap.compress(Bitmap.CompressFormat.JPEG, 85, output))
                output.toByteArray().also { require(it.size <= 2 * 1024 * 1024) { "사진이 2MiB 제한을 초과했습니다." } }
            } finally { bitmap.recycle() }
        }
    }
    fun peek(): SnapshotRequest? = pending.get()?.also {
        if (SystemClock.elapsedRealtime() > it.deadlineMs) fail(it, "카메라 촬영 시간이 초과되었습니다.")
    }?.takeIf { pending.get() === it }
    fun complete(request: SnapshotRequest, snapshot: RawSnapshot) {
        if (pending.compareAndSet(request, null)) request.result.complete(snapshot)
    }
    fun fail(request: SnapshotRequest, message: String) {
        if (pending.compareAndSet(request, null)) request.result.completeExceptionally(IllegalStateException(message))
    }
    fun cancel() {
        pending.getAndSet(null)?.result?.completeExceptionally(IllegalStateException("카메라가 중지되어 촬영을 취소했습니다."))
    }
    companion object {
        fun copy(image: Image): YuvFrame {
            require(image.format == ImageFormat.YUV_420_888 && image.planes.size == 3)
            require(image.width in 1..4096 && image.height in 1..4096 &&
                image.width.toLong() * image.height <= 8_388_608)
            val planes = image.planes.map {
                val buffer = it.buffer.duplicate()
                require(buffer.remaining() <= 16 * 1024 * 1024)
                val bytes = ByteArray(buffer.remaining())
                buffer.get(bytes)
                YuvPlane(bytes, it.rowStride, it.pixelStride)
            }
            return YuvFrame(image.width, image.height, planes[0], planes[1], planes[2])
        }
    }
}
