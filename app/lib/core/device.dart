// Phone-side helpers (Android): speech in and out, storage folder, Wi-Fi lock.
// Implemented in MainActivity.kt without extra packages.
import 'package:flutter/services.dart';

class PhoneDevice {
  static const _channel = MethodChannel('rishu/device');

  static Future<String> filesDir() async => (await _channel.invokeMethod<String>('filesDir')) ?? '';

  static Future<String> deviceName() async {
    try {
      return (await _channel.invokeMethod<String>('deviceName')) ?? 'Android phone';
    } catch (_) {
      return 'Android phone';
    }
  }

  static Future<void> multicast(bool on) async {
    try {
      await _channel.invokeMethod('multicast', {'on': on});
    } catch (_) {}
  }

  /// Listen once with the phone's speech recognizer; '' when nothing was heard.
  static Future<String> listen(String lang) async => (await _channel.invokeMethod<String>('listen', {'lang': lang})) ?? '';

  static Future<void> stopListening() async {
    try {
      await _channel.invokeMethod('stopListening');
    } catch (_) {}
  }

  static Future<void> speak(String text, String lang) async {
    try {
      await _channel.invokeMethod('speak', {'text': text, 'lang': lang});
    } catch (_) {}
  }

  static Future<void> stopSpeaking() async {
    try {
      await _channel.invokeMethod('stopSpeaking');
    } catch (_) {}
  }
}
