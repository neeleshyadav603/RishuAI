package com.rishuai.rishu

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Bundle
import android.provider.AlarmClock
import android.provider.ContactsContract
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.security.KeyStore
import java.util.Locale
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Phone-side helpers for Rishu without extra packages: Android's own speech
 * recognizer (Hindi / Indian English) and text-to-speech; API keys encrypted
 * with a key in the Android Keystore; phone actions through standard intents
 * (alarm, timer, open an app or link, dialer, WhatsApp chat with text typed,
 * contacts lookup); the app storage folder and a Wi-Fi multicast lock.
 * Calls and WhatsApp messages are never sent by Rishu: the user presses the button.
 */
class MainActivity : FlutterActivity() {
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var pendingListen: Pair<MethodCall, MethodChannel.Result>? = null
    private var pendingContact: Pair<MethodCall, MethodChannel.Result>? = null
    private var multicastLock: WifiManager.MulticastLock? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "rishu/device").setMethodCallHandler { call, result ->
            when (call.method) {
                "filesDir" -> result.success(filesDir.absolutePath)
                "deviceName" -> result.success(android.os.Build.MODEL ?: "Android phone")
                "multicast" -> {
                    setMulticast(call.argument<Boolean>("on") == true)
                    result.success(true)
                }
                "listen" -> listen(call, result)
                "stopListening" -> {
                    recognizer?.stopListening()
                    result.success(true)
                }
                "speak" -> {
                    speak(call.argument<String>("text") ?: "", call.argument<String>("lang") ?: "hi-IN")
                    result.success(true)
                }
                "stopSpeaking" -> {
                    tts?.stop()
                    result.success(true)
                }
                "saveSecret" -> {
                    saveSecret(call.argument<String>("name") ?: "", call.argument<String>("value") ?: "")
                    result.success(true)
                }
                "readSecret" -> result.success(readSecret(call.argument<String>("name") ?: ""))
                "deleteSecret" -> {
                    prefs().edit().remove("secret_" + (call.argument<String>("name") ?: "")).apply()
                    result.success(true)
                }
                "setAlarm" -> start(Intent(AlarmClock.ACTION_SET_ALARM).apply {
                    putExtra(AlarmClock.EXTRA_HOUR, call.argument<Int>("hour") ?: 7)
                    putExtra(AlarmClock.EXTRA_MINUTES, call.argument<Int>("minute") ?: 0)
                    putExtra(AlarmClock.EXTRA_MESSAGE, call.argument<String>("label") ?: "Rishu")
                    putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                }, result)
                "setTimer" -> start(Intent(AlarmClock.ACTION_SET_TIMER).apply {
                    putExtra(AlarmClock.EXTRA_LENGTH, call.argument<Int>("seconds") ?: 60)
                    putExtra(AlarmClock.EXTRA_MESSAGE, call.argument<String>("label") ?: "Rishu")
                    putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                }, result)
                "openUrl" -> start(Intent(Intent.ACTION_VIEW, Uri.parse(call.argument<String>("url") ?: "")), result)
                "dial" -> start(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + (call.argument<String>("number") ?: ""))), result)
                "apps" -> result.success(launcherApps())
                "openApp" -> {
                    val launch = packageManager.getLaunchIntentForPackage(call.argument<String>("package") ?: "")
                    if (launch == null) result.success(false) else start(launch, result)
                }
                "findContact" -> findContact(call, result)
                else -> result.notImplemented()
            }
        }
    }

    private fun start(intent: Intent, result: MethodChannel.Result) {
        try {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            result.success(true)
        } catch (e: Exception) {
            result.success(false)
        }
    }

    private fun launcherApps(): List<Map<String, String>> {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return packageManager.queryIntentActivities(intent, 0).map {
            mapOf("label" to it.loadLabel(packageManager).toString(), "package" to it.activityInfo.packageName)
        }.distinctBy { it["package"] }
    }

    private fun findContact(call: MethodCall, result: MethodChannel.Result) {
        if (checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            pendingContact = Pair(call, result)
            requestPermissions(arrayOf(Manifest.permission.READ_CONTACTS), 8)
            return
        }
        val wanted = (call.argument<String>("name") ?: "").trim()
        val found = mutableListOf<Map<String, String>>()
        val cursor = contentResolver.query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            arrayOf(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, ContactsContract.CommonDataKinds.Phone.NUMBER),
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " LIKE ?",
            arrayOf("%$wanted%"),
            null,
        )
        cursor?.use {
            while (it.moveToNext() && found.size < 10) {
                found.add(mapOf("name" to (it.getString(0) ?: ""), "number" to (it.getString(1) ?: "")))
            }
        }
        result.success(found.distinctBy { it["number"]?.filter { c -> c.isDigit() }?.takeLast(10) })
    }

    // ---- API keys, encrypted with a key that never leaves the Android Keystore ----

    private fun prefs() = getSharedPreferences("rishu", Context.MODE_PRIVATE)

    private fun secretKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getEntry("rishu_secrets", null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder("rishu_secrets", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return generator.generateKey()
    }

    private fun saveSecret(name: String, value: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val data = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs().edit().putString("secret_$name", Base64.encodeToString(data, Base64.NO_WRAP)).apply()
    }

    private fun readSecret(name: String): String? {
        val stored = prefs().getString("secret_$name", null) ?: return null
        return try {
            val data = Base64.decode(stored, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, data.copyOfRange(0, 12)))
            String(cipher.doFinal(data.copyOfRange(12, data.size)), Charsets.UTF_8)
        } catch (e: Exception) {
            null
        }
    }

    private fun setMulticast(on: Boolean) {
        val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        if (on && multicastLock == null) {
            multicastLock = wifi.createMulticastLock("rishu-find-laptop").apply {
                setReferenceCounted(false)
                acquire()
            }
        } else if (!on) {
            multicastLock?.release()
            multicastLock = null
        }
    }

    private fun listen(call: MethodCall, result: MethodChannel.Result) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            pendingListen = Pair(call, result)
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 7)
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            result.error("unavailable", "Speech recognition is not available on this phone", null)
            return
        }
        recognizer?.destroy()
        val rec = SpeechRecognizer.createSpeechRecognizer(this)
        recognizer = rec
        var answered = false
        fun answer(block: () -> Unit) {
            if (!answered) {
                answered = true
                block()
            }
        }
        rec.setRecognitionListener(object : RecognitionListener {
            override fun onResults(results: Bundle?) {
                val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull() ?: ""
                answer { result.success(text) }
            }

            override fun onError(error: Int) {
                answer {
                    if (error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT) {
                        result.success("")
                    } else {
                        result.error("error_$error", "Speech recognition failed ($error)", null)
                    }
                }
            }

            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, call.argument<String>("lang") ?: "hi-IN")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        rec.startListening(intent)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 8) {
            val contact = pendingContact ?: return
            pendingContact = null
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                findContact(contact.first, contact.second)
            } else {
                contact.second.error("permission", "Contacts permission was not given", null)
            }
            return
        }
        val pending = pendingListen ?: return
        pendingListen = null
        if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            listen(pending.first, pending.second)
        } else {
            pending.second.error("permission", "Microphone permission was not given", null)
        }
    }

    private fun speak(text: String, lang: String) {
        val parts = lang.split("-")
        val locale = if (parts.size == 2) Locale(parts[0], parts[1]) else Locale("hi", "IN")
        val engine = tts
        if (engine != null && ttsReady) {
            engine.language = locale
            engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, "rishu")
            return
        }
        tts = TextToSpeech(this) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            if (ttsReady) {
                tts?.language = locale
                tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "rishu")
            }
        }
    }

    override fun onDestroy() {
        recognizer?.destroy()
        tts?.shutdown()
        setMulticast(false)
        super.onDestroy()
    }
}
