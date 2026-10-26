package kr.demo.visualguide

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class DeviceRegistrationUnreadable : Exception(
    "저장된 단말 등록을 복호화할 수 없습니다. 기기 복원/Keystore 키 변경 가능성이 있습니다. " +
        "등록을 삭제하고 새 일회용 코드로 다시 페어링하세요."
)

/** Only ciphertext is persisted. The AES key stays in the app's Android Keystore namespace. */
class SecureDeviceStore(context: Context) {
    private val preferences = context.getSharedPreferences("cloud_device_encrypted", Context.MODE_PRIVATE)
    private val alias = "visual_guide_device_v1"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    fun load(): DeviceRegistration? = synchronized(lock) {
        try {
            val encoded = preferences.getString("sealed", null) ?: return@synchronized null
            val sealed = Base64.decode(encoded, Base64.NO_WRAP)
            require(sealed.size >= 28)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, sealed.copyOfRange(0, 12)))
            cipher.updateAAD(alias.toByteArray())
            val json = JSONObject(cipher.doFinal(sealed.copyOfRange(12, sealed.size)).toString(Charsets.UTF_8))
            DeviceRegistration(
                ApiEndpoint.parse(json.getString("origin")).origin, json.getString("token"),
                json.getLong("expires_at_ms"), identifier(json.getString("device_id")),
                if (json.isNull("session_id")) null else identifier(json.getString("session_id")),
                if (json.isNull("pending")) null else CloudDtos.event(json.getJSONObject("pending")),
            )
        } catch (_: Exception) { throw DeviceRegistrationUnreadable() }
    }
    fun save(value: DeviceRegistration, beforeWrite: () -> Unit = {}) = synchronized(lock) {
        beforeWrite()
        val json = JSONObject().put("origin", value.origin).put("token", value.token)
            .put("expires_at_ms", value.expiresAtMs).put("device_id", value.deviceId)
            .put("session_id", value.sessionId ?: JSONObject.NULL)
            .put("pending", value.pending?.json() ?: JSONObject.NULL)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        cipher.updateAAD(alias.toByteArray())
        val encrypted = cipher.iv + cipher.doFinal(json.toString().toByteArray(Charsets.UTF_8))
        check(preferences.edit().putString("sealed", Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit()) {
            "암호화된 단말 등록을 저장하지 못했습니다."
        }
    }
    fun clear(beforeWrite: () -> Unit = {}) = synchronized(lock) {
        beforeWrite()
        check(preferences.edit().clear().commit())
        KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(alias)
    }
    companion object { private val lock = Any() }
}
