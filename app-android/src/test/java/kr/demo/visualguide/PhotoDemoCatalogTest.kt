package kr.demo.visualguide

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class PhotoDemoCatalogTest {
    private val source get() = File(System.getProperty("demo.assets.dir"), "products/catalog.json").readText()

    @Test fun exactOfficialModelsHaveNoUnreviewedProcedures() {
        assertEquals(setOf("AF90H19D35WN", "LS32HG802SKXKR"),
            PhotoDemoCatalog.parse(source).map { it.model }.toSet())
        for (key in listOf("controls", "image", "steps", "target_id")) {
            val changed = JSONObject(source)
            changed.getJSONArray("products").getJSONObject(0).put(key, "unreviewed")
            assertThrows(IllegalArgumentException::class.java) { PhotoDemoCatalog.parse(changed.toString()) }
        }
    }

    @Test fun wrongModelOrExternalSourceIsRejected() {
        assertThrows(IllegalArgumentException::class.java) {
            PhotoDemoCatalog.parse(source.replace("AF90H19D35WN", "AF-UNKNOWN"))
        }
        assertThrows(IllegalArgumentException::class.java) {
            PhotoDemoCatalog.parse(source.replace("www.samsung.com", "example.com"))
        }
    }

    @Test fun photoRightsAndManualIdentityAreRequiredAndReportsStayManual() {
        val initial = PhotoDemoState()
        for (state in listOf(initial, initial.copy(hasPhoto = true),
            initial.copy(hasPhoto = true, rightsConfirmed = true))) {
            assertFalse(state.canStart)
            assertThrows(IllegalArgumentException::class.java) { state.start() }
            assertThrows(IllegalArgumentException::class.java) { state.report("미해결") }
        }
        val started = initial.copy(hasPhoto = true, rightsConfirmed = true, identityConfirmed = true).start()
        assertEquals("판정 불가", started.report("판정 불가").outcome)
        assertThrows(IllegalArgumentException::class.java) { started.report("AI verified") }
        assertNull(PhotoDemoState().outcome)
        assertFalse(PhotoDemoState().started)
    }

    @Test fun decodingIsBoundedWithoutUpscaling() {
        assertEquals(1, photoSampleSize(400, 640))
        assertEquals(4, photoSampleSize(6000, 3000))
        for ((width, height) in listOf(0 to 100, -1 to 100, 6000 to 4000, Int.MAX_VALUE to Int.MAX_VALUE)) {
            assertThrows(IllegalArgumentException::class.java) { photoSampleSize(width, height) }
        }
    }
}
