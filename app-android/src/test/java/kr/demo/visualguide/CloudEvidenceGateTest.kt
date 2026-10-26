package kr.demo.visualguide

import kr.demo.guide.CaptureScope
import kr.demo.guide.OcrEvidence
import org.junit.Assert.*
import org.junit.Test

class CloudEvidenceGateTest {
    @Test fun numericBoundariesAndWrongStepAreRejected() {
        val gate = CloudEvidenceGate()
        val scope = CaptureScope("temperature", 1)
        assertFalse(gate.observe(OcrEvidence(scope, 1000, "TEMP 124"), scope, "TEMP 24", true, 1000))
        assertFalse(gate.observe(OcrEvidence(scope, 1500, "TEMP 24.5"), scope, "TEMP 24", true, 1500))
        assertFalse(gate.observe(OcrEvidence(scope.copy(epoch = 0), 2000, "TEMP 24"),
            scope, "TEMP 24", true, 2000))
        assertEquals(0, gate.samples)
    }

    @Test fun stableEvidenceFiresOnceWithoutChangingServerState() {
        val gate = CloudEvidenceGate()
        val scope = CaptureScope("power", 2)
        assertFalse(gate.observe(OcrEvidence(scope, 1000, "POWER ON"), scope, "POWER ON", true, 1000))
        assertFalse(gate.observe(OcrEvidence(scope, 1500, "POWER ON"), scope, "POWER ON", true, 1500))
        assertTrue(gate.observe(OcrEvidence(scope, 2000, "POWER ON"), scope, "POWER ON", true, 2000))
        assertFalse(gate.observe(OcrEvidence(scope, 2500, "POWER ON"), scope, "POWER ON", true, 2500))
        gate.reset()
        assertFalse(gate.observe(OcrEvidence(scope, 3000, "POWER ON"), scope, "POWER ON", false, 3000))
        assertEquals(0, gate.samples)
    }
}
