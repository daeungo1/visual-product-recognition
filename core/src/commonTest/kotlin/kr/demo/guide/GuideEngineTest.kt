package kr.demo.guide

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class GuideEngineTest {
    @Test
    fun manualProgressionFinishesWithoutSkipping() {
        val engine = GuideEngine(DemoGuide.guide)
        assertFalse(engine.advanceManual("wrong"))
        DemoGuide.guide.steps.forEach { step ->
            assertEquals(step.id, engine.currentStep?.id)
            assertTrue(engine.advanceManual(step.id))
        }
        assertTrue(engine.finished)
        assertFalse(engine.highlightVisible)
        assertFalse(engine.advanceManual("temperature"))
        assertTrue(engine.history.all { it.source == AdvanceSource.MANUAL })
        engine.reset()
        assertEquals("power", engine.currentStep?.id)
    }

    @Test
    fun badStaleAndLateEvidenceCannotAdvance() {
        val engine = GuideEngine(DemoGuide.guide)
        engine.setTracking(true)
        val scope = engine.scope!!
        assertFalse(engine.observe(OcrEvidence(scope, 100, "POWER ON"), 2000))
        assertFalse(engine.observe(OcrEvidence(scope, 2100, "POWER OFF"), 2100))
        engine.advanceManual("power")
        assertFalse(engine.observe(OcrEvidence(scope, 2200, "POWER ON"), 2200))
        assertEquals("mode", engine.currentStep?.id)
    }

    @Test
    fun stableDistinctFramesAdvanceAndSourcesAreExplicit() {
        val engine = GuideEngine(DemoGuide.guide)
        engine.setTracking(true)
        val scope = engine.scope!!
        assertFalse(engine.observe(OcrEvidence(scope, 1000, "POWER ON"), 1000))
        assertFalse(engine.observe(OcrEvidence(scope, 1000, "POWER ON"), 1000))
        assertFalse(engine.observe(OcrEvidence(scope, 1400, "POWER ON"), 1400))
        assertTrue(engine.observe(OcrEvidence(scope, 1900, "POWER ON"), 1900))
        assertEquals("mode", engine.currentStep?.id)
        assertEquals(AdvanceSource.STABLE_OCR, engine.history.single().source)
    }

    @Test
    fun trackingLossClearsEvidenceAndInvalidatesQueuedResponses() {
        val engine = GuideEngine(DemoGuide.guide)
        engine.setTracking(true)
        val old = engine.scope!!
        engine.observe(OcrEvidence(old, 1000, "POWER ON"), 1000)
        assertTrue(engine.highlightVisible)
        engine.setTracking(false)
        assertFalse(engine.highlightVisible)
        assertFalse(engine.observe(OcrEvidence(old, 1400, "POWER ON"), 1400))
        engine.setTracking(true)
        assertFalse(engine.observe(OcrEvidence(old, 1900, "POWER ON"), 1900))
        assertEquals(0, engine.stableSamples)
    }

    @Test
    fun temperatureDoesNotMatchLargerNumberAndGapsRestartStability() {
        val engine = GuideEngine(DemoGuide.guide)
        engine.advanceManual("power")
        engine.advanceManual("mode")
        engine.setTracking(true)
        val scope = engine.scope!!
        assertFalse(engine.observe(OcrEvidence(scope, 1000, "TEMP 124"), 1000))
        assertEquals(0, engine.stableSamples)
        assertFalse(engine.observe(OcrEvidence(scope, 1050, "TEMP 24.5"), 1050))
        assertEquals(0, engine.stableSamples)
        engine.observe(OcrEvidence(scope, 1100, "TEMP 24"), 1100)
        engine.observe(OcrEvidence(scope, 2500, "TEMP 24"), 2500)
        assertEquals(1, engine.stableSamples)
        assertFalse(engine.finished)
    }

    @Test
    fun resetBackAndFutureSamplesAreScoped() {
        val engine = GuideEngine(DemoGuide.guide)
        engine.setTracking(true)
        val first = engine.scope!!
        assertFalse(engine.observe(OcrEvidence(first, 2000, "POWER ON"), 1999))
        engine.advanceManual("power")
        engine.previous()
        assertFalse(engine.observe(OcrEvidence(first, 2100, "POWER ON"), 2100))
        engine.reset()
        assertEquals("power", engine.currentStep?.id)
        assertEquals(0, engine.history.size)
    }
}
