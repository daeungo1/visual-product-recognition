package kr.demo.visualguide

import org.junit.Assert.*
import org.junit.Test

class Yuv420ConverterTest {
    @Test fun planesHonorRowAndPixelStridesRatherThanAssumingNv21() {
        val frame = YuvFrame(2, 2,
            YuvPlane(byteArrayOf(16, 99, 235.toByte(), 99, 99, 81, 99, 145.toByte()), 5, 2),
            YuvPlane(byteArrayOf(128.toByte()), 1, 1),
            YuvPlane(byteArrayOf(128.toByte()), 1, 1))
        val result = Yuv420Converter.convert(frame)
        assertEquals(2, result.width)
        assertEquals(2, result.height)
        assertEquals(0xff000000.toInt(), result.pixels[0])
        assertEquals(0xffffffff.toInt(), result.pixels[1])
        assertTrue((result.pixels[2] and 0xff) < (result.pixels[3] and 0xff))
    }

    @Test fun colorUsesIndependentUAndVPlanes() {
        val frame = YuvFrame(2, 2, YuvPlane(ByteArray(4) { 81 }, 2, 1),
            YuvPlane(byteArrayOf(90), 1, 1), YuvPlane(byteArrayOf(240.toByte()), 1, 1))
        val color = Yuv420Converter.convert(frame).pixels[0]
        assertTrue((color shr 16 and 0xff) >= 250)
        assertTrue((color and 0xff) <= 5)
    }

    @Test fun cropBoundsRotationAndLongEdgeAreMeasuredInOutputPixels() {
        val frame = YuvFrame(4, 2, YuvPlane(ByteArray(8) { 100 }, 4, 1),
            YuvPlane(ByteArray(2) { 128.toByte() }, 2, 1),
            YuvPlane(ByteArray(2) { 128.toByte() }, 2, 1))
        val crop = Yuv420Converter.convert(frame, PixelRect(0, 0, 2, 2), 1)
        assertEquals(1, crop.width)
        assertEquals(1, crop.height)
        val rotated = Yuv420Converter.rotate(PixelImage(2, 1, intArrayOf(1, 2)), 90)
        assertEquals(1, rotated.width)
        assertEquals(2, rotated.height)
        assertArrayEquals(intArrayOf(1, 2), rotated.pixels)
        assertThrows(IllegalArgumentException::class.java) {
            Yuv420Converter.convert(frame, PixelRect(-1, 0, 2, 2))
        }
        assertThrows(IllegalArgumentException::class.java) {
            Yuv420Converter.convert(frame.copy(y = YuvPlane(byteArrayOf(1), 4, 1)))
        }
    }

    @Test fun actualConvertedDimensionsNeverExceed1024Pixels() {
        val frame = YuvFrame(2048, 1024,
            YuvPlane(ByteArray(2048 * 1024) { 100 }, 2048, 1),
            YuvPlane(ByteArray(1024 * 512) { 128.toByte() }, 1024, 1),
            YuvPlane(ByteArray(1024 * 512) { 128.toByte() }, 1024, 1))
        val converted = Yuv420Converter.convert(frame)
        assertEquals(1024, converted.width)
        assertEquals(512, converted.height)
        assertEquals(1024 * 512, converted.pixels.size)
    }
}
