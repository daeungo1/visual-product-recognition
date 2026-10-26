package kr.demo.guide

/** Single-owner reducer. Call only on one thread; capture scope before asynchronous OCR. */
class GuideEngine(val guide: Guide) {
    init {
        require(guide.steps.isNotEmpty())
        require(guide.steps.map { it.id }.distinct().size == guide.steps.size)
    }

    var stepIndex: Int = 0
        private set
    private var epoch = 0L
    private var tracking = false
    private var firstMatchMs: Long? = null
    private var lastCaptureMs: Long? = null
    private val records = mutableListOf<AdvanceRecord>()
    var stableSamples = 0
        private set

    val history: List<AdvanceRecord> get() = records.toList()
    val currentStep: Step? get() = guide.steps.getOrNull(stepIndex)
    val finished: Boolean get() = currentStep == null
    val scope: CaptureScope? get() = currentStep?.let { CaptureScope(it.id, epoch) }
    val highlightVisible: Boolean get() = tracking && !finished

    fun setTracking(fullTracking: Boolean) {
        if (tracking != fullTracking) {
            tracking = fullTracking
            invalidateEvidence()
        }
    }

    fun invalidateEvidence() {
        epoch++
        firstMatchMs = null
        lastCaptureMs = null
        stableSamples = 0
    }

    fun advanceManual(expectedStepId: String): Boolean {
        if (currentStep?.id != expectedStepId) return false
        advance(AdvanceSource.MANUAL)
        return true
    }

    fun observe(evidence: OcrEvidence, nowMs: Long): Boolean {
        if (!tracking || evidence.scope != scope || evidence.text.length > 2048) return false
        if (evidence.capturedAtMs > nowMs || nowMs - evidence.capturedAtMs > 1500L) return false
        val last = lastCaptureMs
        if (last != null && evidence.capturedAtMs <= last) return false
        if (last != null && evidence.capturedAtMs - last > 1200L) {
            firstMatchMs = null
            stableSamples = 0
        }
        lastCaptureMs = evidence.capturedAtMs
        if (!currentStep!!.expected.containsMatchIn(evidence.text.uppercase())) {
            firstMatchMs = null
            stableSamples = 0
            return false
        }
        if (firstMatchMs == null) firstMatchMs = evidence.capturedAtMs
        stableSamples++
        if (stableSamples < 3 || evidence.capturedAtMs - firstMatchMs!! < 800L) return false
        advance(AdvanceSource.STABLE_OCR)
        return true
    }

    fun previous() {
        if (stepIndex > 0) {
            stepIndex--
            if (records.isNotEmpty()) records.removeAt(records.lastIndex)
        }
        invalidateEvidence()
    }

    fun reset() {
        stepIndex = 0
        records.clear()
        invalidateEvidence()
    }

    private fun advance(source: AdvanceSource) {
        records += AdvanceRecord(currentStep!!.id, source)
        stepIndex++
        invalidateEvidence()
    }
}
