package kr.demo.visualguide

import android.content.Context
import android.speech.tts.TextToSpeech
import kr.demo.guide.SpeechPort
import java.util.Locale

internal class AndroidSpeech(context: Context, private val status: (String, Boolean) -> Unit) : SpeechPort {
    private var engine: TextToSpeech? = null
    private var available = false
    private var closed = false

    init {
        engine = TextToSpeech(context.applicationContext) { result ->
            if (!closed) {
                val language = if (result == TextToSpeech.SUCCESS) engine?.setLanguage(Locale.KOREAN) else null
                available = language != null && language >= TextToSpeech.LANG_AVAILABLE
                status(
                    if (available) "한국어 음성 준비됨" else "한국어 TTS를 사용할 수 없습니다. 기기에 한국어 음성 데이터를 설치하세요.",
                    available,
                )
            }
        }
    }

    override fun speak(text: String) {
        if (!available || closed) return
        val result = engine?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "demo-guide")
        if (result == TextToSpeech.ERROR) status("음성 읽기 실패. 화면 안내를 사용하세요.", false)
    }

    override fun stop() {
        engine?.stop()
    }

    fun close() {
        closed = true
        engine?.stop()
        engine?.shutdown()
        engine = null
    }
}
