package kr.demo.visualguide

import android.content.Context
import kr.demo.guide.DemoGuide
import kr.demo.guide.NormalizedRect
import org.json.JSONArray
import org.json.JSONObject

data class DemoAssets(
    val targetId: String,
    val image: String,
    val physicalWidth: Float,
    val display: NormalizedRect,
    val buttons: Map<String, NormalizedRect>,
    val referenceBytes: ByteArray? = null,
    val demo: Boolean = true,
    val label: String = "합성 DEMO",
) {
    companion object {
        fun load(context: Context): DemoAssets {
            val json = context.assets.open("panel_map.json").bufferedReader().use {
                JSONObject(it.readText())
            }
            require(json.getBoolean("demo"))
            require(json.getString("target_id") == DemoGuide.guide.targetId)
            val buttons = json.getJSONObject("buttons")
            val width = json.getDouble("physical_width_meters").toFloat()
            require(width > 0f && width.isFinite())
            return DemoAssets(
                json.getString("target_id"), json.getString("image"), width,
                rect(json.getJSONArray("display")),
                DemoGuide.guide.steps.associate { step ->
                    step.buttonId to rect(buttons.getJSONArray(step.buttonId))
                },
            )
        }

        private fun rect(array: JSONArray): NormalizedRect {
            require(array.length() == 4)
            return NormalizedRect(
                array.getDouble(0).toFloat(), array.getDouble(1).toFloat(),
                array.getDouble(2).toFloat(), array.getDouble(3).toFloat(),
            )
        }
    }
}
