package kr.demo.visualguide

import java.io.File
import kr.demo.guide.GuideEngine
import kr.demo.guide.OcrEvidence
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class DemoScenarioCatalogTest {
    private fun catalogText() = File(File(requireNotNull(System.getProperty("demo.assets.dir")),
        "scenarios"), "catalog.json").readText()

    @Test fun allFourIssuesUseTheirOwnRegisteredTargetAndMappedSteps() {
        val scenarios = DemoScenarioCatalog.parse(catalogText())
        assertEquals(setOf("aircon", "washer", "refrigerator", "monitor"), scenarios.map { it.id }.toSet())
        val source = JSONObject(catalogText()).getJSONArray("scenarios")
        scenarios.forEachIndexed { index, scenario ->
            assertEquals(scenario.assets.targetId, scenario.guide.targetId)
            assertTrue(scenario.assets.demo)
            assertTrue(scenario.guide.steps.all { scenario.assets.buttons.containsKey(it.buttonId) })
            assertTrue(File(System.getProperty("demo.assets.dir"), scenario.assets.image).isFile)
            val engine = GuideEngine(scenario.guide)
            engine.setTracking(true)
            val originalScope = engine.scope!!
            val controls = source.getJSONObject(index).getJSONArray("controls")
            repeat(controls.length()) { position ->
                val scope = engine.scope!!
                val expected = controls.getJSONObject(position).getString("expected")
                val time = 1000L + position * 2000L
                assertFalse(engine.observe(OcrEvidence(scope, time, "WRONG STATE"), time))
                assertFalse(engine.observe(OcrEvidence(scope, time + 100, expected), time + 100))
                assertFalse(engine.observe(OcrEvidence(scope, time + 500, expected), time + 500))
                assertTrue(engine.observe(OcrEvidence(scope, time + 1000, expected), time + 1000))
            }
            assertTrue(engine.finished)
            engine.setTracking(false)
            assertFalse(engine.highlightVisible)
            assertFalse(engine.observe(OcrEvidence(originalScope, 8000, "POWER ON"), 8000))
        }
    }

    @Test fun uncertainOrMultipleTargetsNeverSelectAProduct() {
        assertNull(uniqueTrackedTarget(false, listOf("synthetic-washer-panel-v1")))
        assertNull(uniqueTrackedTarget(true, emptyList()))
        assertNull(uniqueTrackedTarget(true, listOf("aircon", "monitor")))
        assertEquals("aircon", uniqueTrackedTarget(true, listOf("aircon")))
    }

    @Test fun realProductOrDuplicateTargetCannotEnterSyntheticCatalog() {
        val json = JSONObject(catalogText())
        assertThrows(IllegalArgumentException::class.java) {
            DemoScenarioCatalog.parse(json.put("demo", false).toString())
        }
        val duplicate = JSONObject(catalogText())
        val entries = duplicate.getJSONArray("scenarios")
        entries.getJSONObject(1).put("target_id", entries.getJSONObject(0).getString("target_id"))
        assertThrows(IllegalArgumentException::class.java) { DemoScenarioCatalog.parse(duplicate.toString()) }
    }
}
