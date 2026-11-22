package com.rishuai.rishu

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
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
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
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
 *
 * Offline brain: llama.cpp's server (MIT), built for arm64 in CI and packed as
 * lib/arm64-v8a/libllama_server*.so so Android installs it as an executable
 * file; it runs as a child process on 127.0.0.1 with a model from the app's
 * own folder (downloaded once, or copied from the "offline" APK's assets).
 */
class MainActivity : FlutterActivity() {
    private var recognizer: SpeechRecognizer? = null
    private var localProcess: Process? = null
    private val main = Handler(Looper.getMainLooper())
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
                "localEngine" -> result.success(localEngine())
                "bundledModels" -> result.success(
                    (try { assets.list("models")?.toList() } catch (e: Exception) { null } ?: emptyList())
                        .filter { it.endsWith(".gguf") }
                )
                "copyBundled" -> background(result) {
                    val dest = File(call.argument<String>("dest") ?: "")
                    dest.parentFile?.mkdirs()
                    assets.open("models/" + (call.argument<String>("name") ?: "")).use { input ->
                        dest.outputStream().use { input.copyTo(it, 1 shl 20) }
                    }
                    true
                }
                "sha256" -> background(result) {
                    val digest = MessageDigest.getInstance("SHA-256")
                    File(call.argument<String>("path") ?: "").inputStream().use { input ->
                        val buffer = ByteArray(1 shl 20)
                        while (true) {
                            val n = input.read(buffer)
                            if (n < 0) break
                            digest.update(buffer, 0, n)
                        }
                    }
                    digest.digest().joinToString("") { "%02x".format(it) }
                }
                "startLocal" -> result.success(startLocal(call))
                "stopLocal" -> {
                    stopLocal()
                    result.success(true)
                }
                "localRunning" -> result.success(localAlive())
                else -> result.notImplemented()
            }
        }
    }

    // ---- offline brain ------------------------------------------------------------------

    /** Runs slow work off the main thread and answers on it. */
    private fun background(result: MethodChannel.Result, work: () -> Any?) {
        Thread {
            try {
                val value = work()
                main.post { result.success(value) }
            } catch (e: Exception) {
                main.post { result.error("failed", e.message ?: e.toString(), null) }
            }
        }.start()
    }

    /** The server build that suits this phone's CPU (dot-product instructions or plain ARMv8). */
    private fun localEngine(): Map<String, Any?> {
        if (Build.VERSION.SDK_INT < 28) return mapOf("path" to null, "reason" to "android_too_old")
        val dir = applicationInfo.nativeLibraryDir
        val features = try {
            File("/proc/cpuinfo").readLines().firstOrNull { it.startsWith("Features") } ?: ""
        } catch (e: Exception) {
            ""
        }
        val fast = File(dir, "libllama_server.so")
        val plain = File(dir, "libllama_server_v8.so")
        val chosen = when {
            features.contains("asimddp") && fast.exists() -> fast
            plain.exists() -> plain
            else -> null
        }
        return mapOf(
            "path" to chosen?.absolutePath,
            "reason" to if (chosen == null) "no_engine" else "",
            "cores" to Runtime.getRuntime().availableProcessors(),
        )
    }

    private fun startLocal(call: MethodCall): Boolean {
        stopLocal()
        val server = localEngine()["path"] as String? ?: return false
        val threads = (Runtime.getRuntime().availableProcessors() / 2).coerceIn(2, 4)
        val command = listOf(
            server,
            "-m", call.argument<String>("model") ?: return false,
            "--host", "127.0.0.1",
            "--port", (call.argument<Int>("port") ?: 47911).toString(),
            "-c", (call.argument<Int>("ctx") ?: 6144).toString(),
            "-t", threads.toString(),
            "-ngl", "0",
            "--jinja",
            "--reasoning-format", "deepseek",
            "--chat-template-kwargs", "{\"enable_thinking\": false}",
        )
        return try {
            localProcess = ProcessBuilder(command)
                .directory(filesDir)
                .redirectErrorStream(true)
                .redirectOutput(File(filesDir, "llama-server.log"))
                .start()
            true
        } catch (e: Exception) {
            File(filesDir, "llama-server.log").writeText("could not start: $e")
            false
        }
    }

    private fun localAlive(): Boolean {
        val process = localProcess ?: return false
        return try {
            process.exitValue()
            false
        } catch (e: IllegalThreadStateException) {
            true
        }
    }

    private fun stopLocal() {
        localProcess?.destroy()
        localProcess = null
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
        stopLocal()
        recognizer?.destroy()
        tts?.shutdown()
        setMulticast(false)
        super.onDestroy()
    }
}
