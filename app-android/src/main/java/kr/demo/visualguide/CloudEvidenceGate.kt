package kr.demo.visualguide

import kr.demo.guide.CaptureScope
import kr.demo.guide.OcrEvidence

class CloudEvidenceGate {
    var samples = 0
        private set
    private var first: Long? = null
    private var last: Long? = null
    private var fired = false
    private var activeScope: CaptureScope? = null

    fun reset() {
        samples = 0
        first = null
        last = null
        fired = false
        activeScope = null
    }
    fun observe(evidence: OcrEvidence, scope: CaptureScope, expected: String, full: Boolean, now: Long): Boolean {
        if (activeScope != scope) { reset(); activeScope = scope }
        if (!full || fired || evidence.scope != scope || evidence.text.length > 2048 ||
            evidence.capturedAtMs > now || now - evidence.capturedAtMs > 1500) return false
        val previous = last
        if (previous != null && evidence.capturedAtMs <= previous) return false
        if (previous != null && evidence.capturedAtMs - previous > 1200) { samples = 0; first = null }
        last = evidence.capturedAtMs
        val pattern = expected.trim().split(Regex("\\s+")).joinToString("\\s*") { Regex.escape(it) }
        val matches = Regex("(?<![\\p{L}\\p{N}])$pattern(?![\\p{L}\\p{N}.,])", RegexOption.IGNORE_CASE)
            .containsMatchIn(evidence.text)
        if (!matches) { samples = 0; first = null; return false }
        if (first == null) first = evidence.capturedAtMs
        samples++
        fired = samples >= 3 && evidence.capturedAtMs - first!! >= 800
        return fired
    }
}
