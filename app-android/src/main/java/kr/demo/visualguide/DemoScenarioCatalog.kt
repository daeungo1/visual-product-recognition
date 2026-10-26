package kr.demo.visualguide

import android.content.Context
import kr.demo.guide.Guide
import kr.demo.guide.NormalizedRect
import kr.demo.guide.Step
import org.json.JSONArray
import org.json.JSONObject

data class DemoScenario(
    val id: String,
    val product: String,
    val issue: String,
    val summary: String,
    val assets: DemoAssets,
    val guide: Guide,
)

object DemoScenarioCatalog {
    fun load(context: Context): List<DemoScenario> =
        context.assets.open("scenarios/catalog.json").bufferedReader().use { parse(it.readText()) }

    fun parse(text: String): List<DemoScenario> {
        val catalog = JSONObject(text)
        require(catalog.getBoolean("demo")) { "합성 DEMO 카탈로그만 허용합니다." }
        val entries = catalog.getJSONArray("scenarios")
        require(entries.length() in 1..16)
        return (0 until entries.length()).map { index ->
            val entry = entries.getJSONObject(index)
            val id = identifier(entry.getString("id"))
            val target = identifier(entry.getString("target_id"))
            require(target.startsWith("synthetic-"))
            val image = entry.getString("image")
            require(image == "scenarios/$id.png")
            val controls = entry.getJSONArray("controls")
            require(controls.length() in 1..CloudContractLimits.MAX_GUIDE_STEPS)
            val buttons = linkedMapOf<String, NormalizedRect>()
            val steps = (0 until controls.length()).map { position ->
                val control = controls.getJSONObject(position)
                val button = identifier(control.getString("id"))
                require(!buttons.containsKey(button))
                buttons[button] = rect(control.getJSONArray("rect"))
                val expected = control.getString("expected")
                require(expected.isNotBlank() && expected.length <= 256)
                val pattern = expected.trim().split(Regex("\\s+")).joinToString("\\s*") { Regex.escape(it) }
                val instruction = control.getString("instruction")
                require(instruction.isNotBlank())
                Step(button, button, instruction,
                    Regex("(?<![\\p{L}\\p{N}])$pattern(?![\\p{L}\\p{N}.,])", RegexOption.IGNORE_CASE))
            }
            val product = entry.getString("product")
            val issue = entry.getString("issue")
            val width = entry.getDouble("reference_width_m").toFloat()
            require(width.isFinite() && width > 0f)
            DemoScenario(id, product, issue, entry.getString("summary"),
                DemoAssets(target, image, width, rect(entry.getJSONArray("display")), buttons,
                    label = "합성 $product DEMO"),
                Guide("demo-$id-issue-v1", target, "$product · $issue", steps))
        }.also { scenarios ->
            require(scenarios.map { it.id }.distinct().size == scenarios.size)
            require(scenarios.map { it.assets.targetId }.distinct().size == scenarios.size)
        }
    }

    private fun rect(array: JSONArray): NormalizedRect {
        require(array.length() == 4)
        return NormalizedRect(array.getDouble(0).toFloat(), array.getDouble(1).toFloat(),
            array.getDouble(2).toFloat(), array.getDouble(3).toFloat())
    }
}

internal fun uniqueTrackedTarget(cameraTracking: Boolean, targetIds: List<String>): String? =
    if (cameraTracking) targetIds.distinct().singleOrNull() else null
