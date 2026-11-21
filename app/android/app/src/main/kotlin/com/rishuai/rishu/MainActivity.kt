package com.rishuai.rishu

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.wifi.WifiManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.Locale

/**
 * Phone-side voice for Rishu without extra packages: Android's own speech
 * recognizer (Hindi / Indian English) and text-to-speech, plus small device
 * helpers (app storage folder, a Wi-Fi multicast lock to find the laptop).
 */
class MainActivity : FlutterActivity() {
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var pendingListen: Pair<MethodCall, MethodChannel.Result>? = null
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
                else -> result.notImplemented()
            }
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
