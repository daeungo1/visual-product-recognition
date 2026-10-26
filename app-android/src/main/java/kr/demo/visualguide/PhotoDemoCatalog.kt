package kr.demo.visualguide

import android.content.Context
import org.json.JSONObject
import java.net.URI

data class PhotoDemoProduct(
    val model: String,
    val name: String,
    val category: String,
    val issue: String,
    val photoSourceUrl: String,
    val supportUrl: String,
)

object PhotoDemoCatalog {
    fun load(context: Context): List<PhotoDemoProduct> =
        context.assets.open("products/catalog.json").bufferedReader().use { parse(it.readText()) }

    fun parse(text: String): List<PhotoDemoProduct> {
        val root = JSONObject(text)
        require(root.getString("mode") == "local-photo-reference")
        require(!root.getBoolean("bundled_third_party_photos"))
        val products = root.getJSONArray("products")
        require(products.length() == 2)
        return (0 until products.length()).map { index ->
            val item = products.getJSONObject(index)
            val model = item.getString("model")
            require(model in setOf("AF90H19D35WN", "LS32HG802SKXKR"))
            require(item.getString("review_status") == "reference-only")
            require(listOf("controls", "steps", "target_id", "image").none { item.has(it) })
            fun source(key: String): String = item.getString(key).also {
                val uri = URI(it)
                require(uri.scheme == "https" && uri.host == "www.samsung.com" &&
                    uri.userInfo == null && uri.port == -1 && uri.path.contains(model))
            }
            PhotoDemoProduct(model, item.getString("name"), item.getString("category"),
                item.getString("issue"), source("photo_source_url"), source("support_url"))
        }.also { require(it.map { p -> p.model }.distinct().size == 2) }
    }
}

data class PhotoDemoState(
    val hasPhoto: Boolean = false,
    val rightsConfirmed: Boolean = false,
    val identityConfirmed: Boolean = false,
    val started: Boolean = false,
    val outcome: String? = null,
) {
    val canStart: Boolean get() = hasPhoto && rightsConfirmed && identityConfirmed
    fun start(): PhotoDemoState {
        require(canStart) { "사진·사용권·수동 모델 확인이 필요합니다." }
        return copy(started = true)
    }
    fun report(value: String): PhotoDemoState {
        require(started && canStart)
        require(value in setOf("미해결", "판정 불가", "사용자가 해결되었다고 보고"))
        return copy(outcome = value)
    }
}

internal fun photoSampleSize(width: Int, height: Int): Int {
    require(width > 0 && height > 0 && width.toLong() * height <= 20_000_000) {
        "유효한 JPEG/PNG 20 MP 이하 사진이 필요합니다."
    }
    var sample = 1
    while (maxOf(width, height) / sample > 2048) sample *= 2
    return sample
}
