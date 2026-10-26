package kr.demo.guide

data class Vec3(val x: Float, val y: Float, val z: Float)
data class ScreenPoint(val x: Float, val y: Float)
data class NormalizedRect(val left: Float, val top: Float, val right: Float, val bottom: Float) {
    init {
        require(listOf(left, top, right, bottom).all { it.isFinite() && it in 0f..1f })
        require(left < right && top < bottom)
    }
    fun corners(): List<Pair<Float, Float>> = listOf(
        left to top, right to top, right to bottom, left to bottom,
    )
}

fun imagePoint(u: Float, v: Float, width: Float, height: Float): Vec3 =
    Vec3((u - 0.5f) * width, 0f, (v - 0.5f) * height)

/** Column-major local-image-to-clip matrix; output uses a top-left pixel origin. */
fun project(point: Vec3, matrix: FloatArray, width: Int, height: Int): ScreenPoint? {
    require(matrix.size == 16)
    if (width <= 0 || height <= 0) return null
    val x = matrix[0] * point.x + matrix[4] * point.y + matrix[8] * point.z + matrix[12]
    val y = matrix[1] * point.x + matrix[5] * point.y + matrix[9] * point.z + matrix[13]
    val z = matrix[2] * point.x + matrix[6] * point.y + matrix[10] * point.z + matrix[14]
    val w = matrix[3] * point.x + matrix[7] * point.y + matrix[11] * point.z + matrix[15]
    if (!listOf(x, y, z, w).all { it.isFinite() } || w <= 0f || z / w !in -1f..1f) return null
    return ScreenPoint((x / w + 1f) * width / 2f, (1f - y / w) * height / 2f)
}
