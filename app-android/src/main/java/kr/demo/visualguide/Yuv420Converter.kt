package kr.demo.visualguide

import kotlin.math.max
import kotlin.math.min

data class YuvPlane(val bytes: ByteArray, val rowStride: Int, val pixelStride: Int) {
    fun sample(x: Int, y: Int): Int {
        require(rowStride > 0 && pixelStride > 0)
        val offset = y.toLong() * rowStride + x.toLong() * pixelStride
        require(offset in 0 until bytes.size.toLong()) { "YUV 평면의 stride/길이가 올바르지 않습니다." }
        return bytes[offset.toInt()].toInt() and 0xff
    }
}
data class YuvFrame(val width: Int, val height: Int, val y: YuvPlane, val u: YuvPlane, val v: YuvPlane)
data class PixelRect(val left: Int, val top: Int, val right: Int, val bottom: Int)
data class PixelImage(val width: Int, val height: Int, val pixels: IntArray)

object Yuv420Converter {
    fun convert(frame: YuvFrame, crop: PixelRect = PixelRect(0, 0, frame.width, frame.height),
                maxEdge: Int = 1024): PixelImage {
        require(frame.width in 1..4096 && frame.height in 1..4096 &&
            frame.width.toLong() * frame.height <= 8_388_608 && maxEdge in 1..1024)
        require(crop.left >= 0 && crop.top >= 0 && crop.right <= frame.width &&
            crop.bottom <= frame.height && crop.left < crop.right && crop.top < crop.bottom)
        // Validate the final addressed samples, including independently padded/interleaved chroma.
        frame.y.sample(frame.width - 1, frame.height - 1)
        frame.u.sample((frame.width - 1) / 2, (frame.height - 1) / 2)
        frame.v.sample((frame.width - 1) / 2, (frame.height - 1) / 2)
        val width = crop.right - crop.left
        val height = crop.bottom - crop.top
        val scale = min(1.0, maxEdge.toDouble() / max(width, height))
        val outWidth = max(1, (width * scale).toInt())
        val outHeight = max(1, (height * scale).toInt())
        val pixels = IntArray(outWidth * outHeight)
        for (y in 0 until outHeight) for (x in 0 until outWidth) {
            val sx = crop.left + x * width / outWidth
            val sy = crop.top + y * height / outHeight
            val luma = max(0, frame.y.sample(sx, sy) - 16)
            val u = frame.u.sample(sx / 2, sy / 2) - 128
            val v = frame.v.sample(sx / 2, sy / 2) - 128
            val red = ((298 * luma + 409 * v + 128) shr 8).coerceIn(0, 255)
            val green = ((298 * luma - 100 * u - 208 * v + 128) shr 8).coerceIn(0, 255)
            val blue = ((298 * luma + 516 * u + 128) shr 8).coerceIn(0, 255)
            pixels[y * outWidth + x] = (0xff shl 24) or (red shl 16) or (green shl 8) or blue
        }
        return PixelImage(outWidth, outHeight, pixels)
    }
    fun rotate(image: PixelImage, degrees: Int): PixelImage {
        require(degrees in listOf(0, 90, 180, 270))
        if (degrees == 0) return image
        val width = if (degrees == 180) image.width else image.height
        val height = if (degrees == 180) image.height else image.width
        val pixels = IntArray(image.pixels.size)
        for (y in 0 until image.height) for (x in 0 until image.width) {
            val dx = when (degrees) { 90 -> image.height - 1 - y; 180 -> image.width - 1 - x; else -> y }
            val dy = when (degrees) { 90 -> x; 180 -> image.height - 1 - y; else -> image.width - 1 - x }
            pixels[dy * width + dx] = image.pixels[y * image.width + x]
        }
        return PixelImage(width, height, pixels)
    }
}
