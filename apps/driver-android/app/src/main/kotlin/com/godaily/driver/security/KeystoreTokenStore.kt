package com.godaily.driver.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.godaily.driver.core.api.TokenProvider
import java.security.GeneralSecurityException
import java.security.KeyStore
import java.time.Instant
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Session token encrypted with an AES-256-GCM key that lives in the Android
 * Keystore (hardware-backed where available) and never leaves it. Only the
 * ciphertext is written to app-private preferences, which are excluded from
 * backups. The token is never logged.
 */
class KeystoreTokenStore(context: Context) : TokenProvider {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    @Volatile
    private var cached: String? = null

    val driverName: String? get() = prefs.getString(KEY_NAME, null)

    val expiresAt: Instant?
        get() = prefs.getLong(KEY_EXPIRES, 0L).takeIf { it > 0 }?.let(Instant::ofEpochMilli)

    fun isLoggedIn(now: Instant = Instant.now()): Boolean {
        val expiry = expiresAt ?: return false
        return expiry.isAfter(now) && token() != null
    }

    @Synchronized
    fun save(token: String, expiresAt: Instant, driverName: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val ciphertext = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString(KEY_IV, encode(cipher.iv))
            .putString(KEY_TOKEN, encode(ciphertext))
            .putLong(KEY_EXPIRES, expiresAt.toEpochMilli())
            .putString(KEY_NAME, driverName)
            .apply()
        cached = token
    }

    @Synchronized
    override fun token(): String? {
        cached?.let { return it }
        val iv = prefs.getString(KEY_IV, null) ?: return null
        val ciphertext = prefs.getString(KEY_TOKEN, null) ?: return null
        return try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(GCM_TAG_BITS, decode(iv)))
            String(cipher.doFinal(decode(ciphertext)), Charsets.UTF_8).also { cached = it }
        } catch (_: GeneralSecurityException) {
            // Key invalidated (e.g. device credentials reset): force a new login.
            clear()
            null
        } catch (_: IllegalArgumentException) {
            clear()
            null
        }
    }

    @Synchronized
    fun clear() {
        cached = null
        prefs.edit().clear().apply()
    }

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    private fun encode(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)

    private fun decode(text: String) = Base64.decode(text, Base64.NO_WRAP)

    private companion object {
        const val PREFS = "gd_auth"
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "gd_session_token_key"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_TAG_BITS = 128
        const val KEY_IV = "iv"
        const val KEY_TOKEN = "token"
        const val KEY_EXPIRES = "expires_at"
        const val KEY_NAME = "driver_name"
    }
}
