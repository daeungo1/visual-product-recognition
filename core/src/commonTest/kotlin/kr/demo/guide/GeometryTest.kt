package kr.demo.guide

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class GeometryTest {
    private val identity = floatArrayOf(
        1f, 0f, 0f, 0f, 0f, 1f, 0f, 0f,
        0f, 0f, 1f, 0f, 0f, 0f, 0f, 1f,
    )

    @Test
    fun normalizedCoordinatesUseImageCenterAndDownwardZ() {
        assertEquals(Vec3(-1f, 0f, -2f), imagePoint(0f, 0f, 2f, 4f))
        assertEquals(Vec3(1f, 0f, 2f), imagePoint(1f, 1f, 2f, 4f))
    }

    @Test
    fun projectionFlipsNdcYIntoTopLeftScreenCoordinates() {
        assertEquals(ScreenPoint(100f, 50f), project(Vec3(0f, 0f, 0f), identity, 200, 100))
        assertEquals(ScreenPoint(200f, 0f), project(Vec3(1f, 1f, 0f), identity, 200, 100))
        assertNull(project(Vec3(0f, 0f, 2f), identity, 200, 100))
        val behind = identity.copyOf().also { it[15] = -1f }
        assertNull(project(Vec3(0f, 0f, 0f), behind, 200, 100))
    }
}
