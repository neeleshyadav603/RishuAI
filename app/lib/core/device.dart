// Phone-side helpers (Android): speech in and out, storage folder, Wi-Fi lock,
// encrypted key storage and phone actions (alarm, timer, apps, links, dialer, contacts).
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

  // ---- secrets (Android Keystore) ----------------------------------------------

  static Future<void> saveSecret(String name, String value) async {
    await _channel.invokeMethod('saveSecret', {'name': name, 'value': value});
  }

  static Future<String?> readSecret(String name) async {
    try {
      return await _channel.invokeMethod<String>('readSecret', {'name': name});
    } catch (_) {
      return null;
    }
  }

  static Future<void> deleteSecret(String name) async {
    await _channel.invokeMethod('deleteSecret', {'name': name});
  }

  // ---- phone actions ---------------------------------------------------------------

  static Future<bool> _ok(String method, [Map<String, Object?>? args]) async {
    try {
      return (await _channel.invokeMethod<bool>(method, args)) ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> setAlarm(int hour, int minute, String label) =>
      _ok('setAlarm', {'hour': hour, 'minute': minute, 'label': label});

  static Future<bool> setTimer(int seconds, String label) => _ok('setTimer', {'seconds': seconds, 'label': label});

  static Future<bool> openUrl(String url) => _ok('openUrl', {'url': url});

  static Future<bool> dial(String number) => _ok('dial', {'number': number});

  static Future<bool> openApp(String package) => _ok('openApp', {'package': package});

  static Future<List<Map<String, String>>> apps() async {
    final raw = await _channel.invokeMethod<List<Object?>>('apps') ?? const [];
    return [
      for (final a in raw)
        if (a is Map) {'label': '${a['label'] ?? ''}', 'package': '${a['package'] ?? ''}'}
    ];
  }

  static Future<List<Map<String, String>>> findContact(String name) async {
    final raw = await _channel.invokeMethod<List<Object?>>('findContact', {'name': name}) ?? const [];
    return [
      for (final c in raw)
        if (c is Map) {'name': '${c['name'] ?? ''}', 'number': '${c['number'] ?? ''}'}
    ];
  }

  // ---- offline brain (llama.cpp server on the phone) --------------------------------

  static Future<Map<String, dynamic>> localEngine() async {
    try {
      return Map<String, dynamic>.from(await _channel.invokeMethod<Map<Object?, Object?>>('localEngine') ?? const {});
    } catch (_) {
      return const {};
    }
  }

  static Future<List<String>> bundledModels() async {
    try {
      return [for (final m in await _channel.invokeMethod<List<Object?>>('bundledModels') ?? const []) '$m'];
    } catch (_) {
      return const [];
    }
  }

  static Future<bool> copyBundled(String name, String dest) =>
      _ok('copyBundled', {'name': name, 'dest': dest});

  static Future<String?> sha256File(String path) => _channel.invokeMethod<String>('sha256', {'path': path});

  static Future<bool> startLocal(String model, int port, int ctx) =>
      _ok('startLocal', {'model': model, 'port': port, 'ctx': ctx});

  static Future<void> stopLocal() async {
    await _channel.invokeMethod('stopLocal');
  }

  static Future<bool> localRunning() => _ok('localRunning');
}

