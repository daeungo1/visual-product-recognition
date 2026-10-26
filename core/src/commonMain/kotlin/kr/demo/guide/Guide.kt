package kr.demo.guide

data class Step(val id: String, val buttonId: String, val instruction: String, val expected: Regex)
data class Guide(val id: String, val targetId: String, val title: String, val steps: List<Step>)
data class CaptureScope(val stepId: String, val epoch: Long)
data class OcrEvidence(val scope: CaptureScope, val capturedAtMs: Long, val text: String)
enum class AdvanceSource { MANUAL, STABLE_OCR }
data class AdvanceRecord(val stepId: String, val source: AdvanceSource)

interface SpeechPort {
    fun speak(text: String)
    fun stop()
}

interface GuideCatalogPort {
    fun guides(): List<Guide>
}

object DemoGuide : GuideCatalogPort {
    val guide = Guide(
        id = "demo-aircon",
        targetId = "original-demo-remote-v1",
        title = "합성 에어컨: 냉방 24도",
        steps = listOf(
            Step("power", "power", "두 번째 화면의 전원 버튼을 눌러 POWER ON으로 바꾸세요.",
                Regex("""(?<![A-Z0-9])POWER\s*[:=]?\s*ON(?![A-Z0-9])""")),
            Step("mode", "mode", "모드 버튼을 눌러 MODE COOL로 바꾸세요.",
                Regex("""(?<![A-Z0-9])MODE\s*[:=]?\s*COOL(?![A-Z0-9])""")),
            Step("temperature", "temperature", "온도 버튼을 눌러 TEMP 24로 바꾸세요.",
                Regex("""(?<![A-Z0-9])TEMP\s*[:=]?\s*24(?![A-Z0-9.,])""")),
        ),
    )

    override fun guides(): List<Guide> = listOf(guide)
}
