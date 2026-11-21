// App state: the conversation, the orb, settings, and every event from the core.
import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../core/connection.dart';
import '../core/device.dart';
import '../core/remote.dart';

enum Phase { booting, failed, onboarding, ready, pairing }

enum OrbMood { connecting, idle, listening, thinking, acting, speaking, offline, locked }

OrbMood moodFrom(String? state) => switch (state) {
      'listening' => OrbMood.listening,
      'thinking' => OrbMood.thinking,
      'acting' => OrbMood.acting,
      'speaking' => OrbMood.speaking,
      'offline' => OrbMood.offline,
      'locked' => OrbMood.locked,
      _ => OrbMood.idle,
    };

int _ids = 0;

abstract class ChatItem {
  ChatItem() : id = ++_ids, time = DateTime.now();
  final int id;
  final DateTime time;
}

class UserItem extends ChatItem {
  UserItem(this.text, {this.voice = false});
  final String text;
  final bool voice;
}

class AssistantItem extends ChatItem {
  AssistantItem(this.text, {this.streaming = false});
  String text;
  bool streaming;
  String provider = '';
  String model = '';
}

enum ToolStatus { running, done, failed, denied }

class ToolItem extends ChatItem {
  ToolItem(this.callId, this.tool, this.message);
  final String callId;
  final String tool;
  String message;
  ToolStatus status = ToolStatus.running;
  String summary = '';
}

enum ApprovalStatus { pending, approved, denied, expired, blocked }

class ApprovalItem extends ChatItem {
  ApprovalItem({
    required this.callId,
    required this.tool,
    required this.preview,
    required this.risk,
    required this.decision,
    required this.reason,
    required this.timeoutSeconds,
    this.stepUpReady = false,
  });
  final bool stepUpReady;
  final String callId;
  final String tool;
  final String preview;
  final String risk;
  final String decision;
  final String reason;
  final double timeoutSeconds;
  ApprovalStatus status = ApprovalStatus.pending;
}

class Source {
  Source(this.title, this.url);
  final String title;
  final String url;
}

class SourcesItem extends ChatItem {
  SourcesItem(this.sources);
  final List<Source> sources;
}

class NoticeItem extends ChatItem {
  NoticeItem(this.text, {this.error = false, this.reminder = false});
  final String text;
  final bool error;
  final bool reminder;
}

class Provider {
  Provider(Map<String, dynamic> j)
      : name = '${j['name'] ?? ''}',
        label = '${j['label'] ?? j['name'] ?? ''}',
        local = j['local'] == true,
        keyUrl = '${j['key_url'] ?? ''}',
        configured = j['configured'] == true,
        keySource = j['key_source'] as String?;
  final String name;
  final String label;
  final bool local;
  final String keyUrl;
  final bool configured;
  final String? keySource;
}

class VoiceCaps {
  VoiceCaps([Map<String, dynamic>? j])
      : input = j?['input'] == true,
        inputReason = '${j?['input_reason'] ?? ''}',
        output = j?['output'] == true,
        hotkey = '${j?['hotkey'] ?? ''}';
  final bool input;
  final String inputReason;
  final bool output;
  final String hotkey;
}

/// The core's lock status (PIN, spoken password, Windows Hello).
class LockInfo {
  LockInfo([Map<String, dynamic>? e])
      : locked = e?['locked'] == true,
        pinSet = e?['pin_set'] == true,
        phraseSet = e?['phrase_set'] == true,
        hello = e?['hello'] == true,
        idleMinutes = ((e?['idle_minutes'] as num?) ?? 10).toDouble(),
        pausedSeconds = ((e?['paused_seconds'] as num?) ?? 0).toInt();
  final bool locked;
  final bool pinSet;
  final bool phraseSet;
  final bool hello;
  final double idleMinutes;
  final int pausedSeconds;
}

/// Teach mode: Rishu is recording a task the user shows; taught skills.
class TeachInfo {
  TeachInfo([Map<String, dynamic>? e])
      : recording = e?['recording'] == true,
        task = '${e?['task'] ?? ''}',
        steps = [for (final s in (e?['steps'] as List?) ?? const []) '$s'],
        skills = _skills(e?['skills']);

  static List<({String name, String description, int steps})> _skills(Object? raw) {
    final out = <({String name, String description, int steps})>[];
    if (raw is! List) return out;
    for (final k in raw) {
      if (k is! Map) continue;
      final steps = k['steps'];
      out.add((name: '${k['name'] ?? ''}', description: '${k['description'] ?? ''}', steps: steps is num ? steps.toInt() : 0));
    }
    return out;
  }

  final bool recording;
  final String task;
  final List<String> steps;
  final List<({String name, String description, int steps})> skills;
}

/// Rishu's offline model: engine bundled, file downloaded, progress.
class LocalModelInfo {
  LocalModelInfo([Map<String, dynamic>? e])
      : engine = e?['engine'] == true,
        choice = '${e?['choice'] ?? 'small'}',
        choices = {
          for (final entry in ((e?['choices'] as Map?) ?? const {}).entries) '${entry.key}': '${entry.value}'
        },
        downloaded = e?['downloaded'] == true,
        sizeMb = ((e?['size_mb'] as num?) ?? 0).toInt(),
        running = e?['running'] == true,
        done = (((e?['progress'] as Map?)?['done'] as num?) ?? 0).toInt(),
        total = (((e?['progress'] as Map?)?['total'] as num?) ?? 0).toInt(),
        downloading = e?['progress'] is Map,
        error = '${e?['error'] ?? ''}';
  final bool engine;
  final String choice;
  final Map<String, String> choices;
  final bool downloaded;
  final int sizeMb;
  final bool running;
  final bool downloading;
  final int done;
  final int total;
  final String error;
  double get fraction => total > 0 ? done / total : 0;
}

/// The laptop's phone link (Windows side).
class PhoneLinkInfo {
  PhoneLinkInfo([Map<String, dynamic>? e, this.code = '', this.codeUntil])
      : running = e?['running'] == true,
        port = ((e?['port'] as num?) ?? 47800).toInt(),
        addresses = [for (final a in (e?['addresses'] as List?) ?? const []) '$a'],
        pairing = e?['pairing'] == true,
        devices = [
          for (final d in (e?['devices'] as List?) ?? const [])
            if (d is Map) {'id': '${d['id'] ?? ''}', 'name': '${d['name'] ?? ''}'}
        ];
  final bool running;
  final int port;
  final List<String> addresses;
  final bool pairing;
  final List<Map<String, String>> devices;
  final String code;
  final DateTime? codeUntil;
}

typedef Connector = Future<CoreConnection> Function();

/// Android: the paired laptop's Rishu over the home Wi-Fi.
Future<CoreConnection> connectToPairedLaptop() async {
  final endpoint = PairingStore(Directory(await PhoneDevice.filesDir())).load();
  if (endpoint == null) throw NeedsPairing();
  return RemoteConnection.open(endpoint);
}

Future<CoreConnection> connectToBundledCore() async {
  if (Platform.isAndroid) return connectToPairedLaptop();
  final endpoint = await CoreLauncher.start();
  try {
    return await WebSocketConnection.open(endpoint);
  } catch (e) {
    endpoint.process?.kill();
    throw CoreStartException('Rishu ke core se connect nahi ho paaya: $e');
  }
}

class AssistantController extends ChangeNotifier {
  AssistantController({Connector? connector}) : _connector = connector ?? connectToBundledCore;

  final Connector _connector;
  CoreConnection? _core;
  StreamSubscription<Map<String, dynamic>>? _sub;

  Phase phase = Phase.booting;
  String bootError = '';
  String version = '';
  OrbMood mood = OrbMood.connecting;
  double level = 0;
  final List<ChatItem> items = [];
  Map<String, dynamic> settings = {};
  List<Provider> providers = [];
  VoiceCaps voice = VoiceCaps();
  LockInfo lock = LockInfo();
  TeachInfo teach = TeachInfo();
  LocalModelInfo localModel = LocalModelInfo();
  PhoneLinkInfo phoneLink = PhoneLinkInfo();
  String lockError = '';
  double approvalTimeout = 120;
  bool disconnected = false;
  bool _skippedSetup = false;
  bool _greeted = false;
  AssistantItem? _streaming;

  // ---- derived ----------------------------------------------------------

  bool get hasBrain => providers.any((p) => p.configured && !p.local);
  bool get listening => mood == OrbMood.listening;
  bool get busy => mood == OrbMood.thinking || mood == OrbMood.acting;
  bool get canStop => busy || mood == OrbMood.speaking || listening;
  bool get speakReplies => settings['speak_replies'] != false;
  String get userName => '${settings['user_name'] ?? ''}';
  String get language => '${settings['language'] ?? 'auto'}';
  bool get english => language == 'en';
  bool get locked => lock.locked;

  // ---- lifecycle --------------------------------------------------------

  Future<void> boot() async {
    phase = Phase.booting;
    mood = OrbMood.connecting;
    bootError = '';
    disconnected = false;
    notifyListeners();
    try {
      final core = await _connector();
      _core = core;
      await _sub?.cancel();
      _sub = core.events.listen(_onEvent, onDone: _onDisconnected);
    } on NeedsPairing {
      phase = Phase.pairing;
      mood = OrbMood.idle;
      notifyListeners();
    } catch (e) {
      phase = Phase.failed;
      bootError = '$e';
      mood = OrbMood.offline;
      notifyListeners();
    }
  }

  void _onDisconnected() {
    if (phase == Phase.booting) {
      phase = Phase.failed;
      bootError = 'Rishu ka core band ho gaya.';
    }
    disconnected = true;
    mood = OrbMood.offline;
    notifyListeners();
  }

  Future<void> restart() async {
    await _sub?.cancel();
    _sub = null;
    try {
      await _core?.close();
    } catch (_) {}
    _core = null;
    await boot();
  }

  @override
  void dispose() {
    _sub?.cancel();
    _core?.close();
    super.dispose();
  }

  // ---- events from the core ----------------------------------------------

  void _onEvent(Map<String, dynamic> e) {
    switch (e['type']) {
      case 'hello':
        _hello(e);
      case 'state_change':
        mood = moodFrom(e['state'] as String?);
        if (mood != OrbMood.listening) level = 0;
        if (mood == OrbMood.idle) _finishStreaming();
      case 'audio_level':
        level = ((e['level'] as num?) ?? 0).toDouble().clamp(0.0, 1.0);
      case 'transcript_final':
        final text = '${e['text'] ?? ''}'.trim();
        if (text.isNotEmpty) items.add(UserItem(text, voice: true));
      case 'assistant_token':
        _token(e);
      case 'assistant_message':
        _message(e);
        if (onPhone && speakReplies) unawaited(PhoneDevice.speak('${e['text'] ?? ''}', _speechLang));
      case 'tool_progress':
        _toolProgress(e);
      case 'tool_result':
        _toolResult(e);
      case 'tool_call_proposed':
        _proposal(e);
      case 'card':
        _card(e);
      case 'notice':
        items.add(NoticeItem('${e['text'] ?? ''}'));
      case 'reminder':
        items.add(NoticeItem('⏰ ${e['text'] ?? ''}', reminder: true));
        if (onPhone) unawaited(PhoneDevice.speak('${e['text'] ?? ''}', _speechLang));
      case 'lock_state':
        _lockState(e);
      case 'teach_state':
        teach = TeachInfo(e);
      case 'local_model':
        localModel = LocalModelInfo(e);
      case 'phone_link':
        phoneLink = PhoneLinkInfo(e, e['pairing'] == true ? phoneLink.code : '', phoneLink.codeUntil);
      case 'error':
        final code = '${e['code'] ?? ''}';
        if (locked && (code == 'locked' || code.startsWith('unlock_') || code.startsWith('voice_'))) {
          lockError = '${e['message'] ?? ''}';
        } else if (code != 'no_such_approval') {
          items.add(NoticeItem('${e['message'] ?? 'Kuch gadbad ho gayi.'}', error: true));
        }
      case 'voice_status':
        voice = VoiceCaps(e);
      default:
        return;
    }
    notifyListeners();
  }

  void _hello(Map<String, dynamic> e) {
    version = '${e['version'] ?? ''}';
    settings = Map<String, dynamic>.from(e['settings'] as Map? ?? {});
    providers = [for (final p in (e['providers'] as List? ?? [])) Provider(Map<String, dynamic>.from(p as Map))];
    final caps = Map<String, dynamic>.from(e['capabilities'] as Map? ?? {});
    voice = VoiceCaps(caps['voice'] is Map ? Map<String, dynamic>.from(caps['voice'] as Map) : null);
    approvalTimeout = ((caps['approval_timeout_seconds'] as num?) ?? 120).toDouble();
    lock = LockInfo(e['lock'] is Map ? Map<String, dynamic>.from(e['lock'] as Map) : null);
    teach = TeachInfo(e['teach'] is Map ? Map<String, dynamic>.from(e['teach'] as Map) : null);
    localModel = LocalModelInfo(e['local_model'] is Map ? Map<String, dynamic>.from(e['local_model'] as Map) : null);
    disconnected = false;
    mood = OrbMood.idle;
    final firstRun = !hasBrain && userName.isEmpty && !_skippedSetup;
    phase = firstRun ? Phase.onboarding : Phase.ready;
    if (phase == Phase.ready && !lock.locked) _greet();
  }

  /// Rishu says hello aloud once per launch (only when replies are spoken).
  void _greet() {
    if (_greeted || !speakReplies || !voice.output) return;
    _greeted = true;
    final hour = DateTime.now().hour;
    final name = userName.isEmpty ? '' : ' $userName';
    final text = english
        ? '${hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'}$name! I am Rishu. How can I help?'
        : '${hour < 12 ? 'सुप्रभात' : hour < 17 ? 'नमस्ते' : 'शुभ संध्या'}$name! मैं रिशु हूँ। बताइए, क्या करना है?';
    _core?.send({'type': 'speak', 'text': text});
  }

  void _lockState(Map<String, dynamic> e) {
    final wasLocked = lock.locked;
    lock = LockInfo(e);
    if (lock.locked && !wasLocked) {
      // Nothing private stays on screen behind the lock.
      items.clear();
      _streaming = null;
      lockError = '';
    }
    if (!lock.locked) lockError = '';
    if (wasLocked && !lock.locked && phase == Phase.ready) _greet();
  }

  void _token(Map<String, dynamic> e) {
    if (e['reset'] == true) {
      if (_streaming != null) {
        items.remove(_streaming);
        _streaming = null;
      }
      return;
    }
    final text = '${e['text'] ?? ''}';
    if (text.isEmpty) return;
    final current = _streaming;
    if (current == null) {
      final item = AssistantItem(text, streaming: true);
      _streaming = item;
      items.add(item);
    } else {
      current.text += text;
    }
  }

  void _message(Map<String, dynamic> e) {
    final text = '${e['text'] ?? ''}';
    final current = _streaming;
    if (current != null) {
      current.text = text;
      current.streaming = false;
      current.provider = '${e['provider'] ?? ''}';
      current.model = '${e['model'] ?? ''}';
      _streaming = null;
    } else if (text.isNotEmpty) {
      items.add(AssistantItem(text)
        ..provider = '${e['provider'] ?? ''}'
        ..model = '${e['model'] ?? ''}');
    }
  }

  void _finishStreaming() {
    final current = _streaming;
    if (current != null) {
      current.streaming = false;
      _streaming = null;
    }
  }

  ToolItem? _tool(String callId) {
    for (final item in items.reversed) {
      if (item is ToolItem && item.callId == callId) return item;
    }
    return null;
  }

  ApprovalItem? approval(String callId) {
    for (final item in items.reversed) {
      if (item is ApprovalItem && item.callId == callId) return item;
    }
    return null;
  }

  void _toolProgress(Map<String, dynamic> e) {
    final callId = '${e['call_id'] ?? ''}';
    final status = e['status'];
    final tool = _tool(callId);
    if (status == 'started') {
      // A tool call shows up as a running step after its text preamble.
      _finishStreaming();
      if (tool == null) items.add(ToolItem(callId, '${e['tool'] ?? ''}', '${e['message'] ?? ''}'));
    } else if (status == 'denied') {
      if (tool != null) {
        tool.status = ToolStatus.denied;
      }
      final card = approval(callId);
      if (card != null && card.status == ApprovalStatus.pending) {
        card.status = card.decision == 'step_up' ? ApprovalStatus.blocked : ApprovalStatus.denied;
      }
    }
  }

  void _toolResult(Map<String, dynamic> e) {
    final tool = _tool('${e['call_id'] ?? ''}');
    if (tool == null) return;
    tool.status = e['ok'] == true ? ToolStatus.done : ToolStatus.failed;
    tool.summary = '${e['summary'] ?? ''}';
  }

  void _proposal(Map<String, dynamic> e) {
    _finishStreaming();
    final item = ApprovalItem(
      callId: '${e['call_id'] ?? ''}',
      tool: '${e['tool'] ?? ''}',
      preview: '${e['preview'] ?? ''}',
      risk: '${e['risk'] ?? ''}',
      decision: '${e['decision'] ?? 'confirm'}',
      reason: '${e['reason'] ?? ''}',
      timeoutSeconds: approvalTimeout,
      stepUpReady: e['step_up_ready'] == true,
    );
    if (item.decision == 'step_up' && !item.stepUpReady) item.status = ApprovalStatus.blocked;
    items.add(item);
  }

  void _card(Map<String, dynamic> e) {
    if (e['card'] != 'sources') return;
    final data = Map<String, dynamic>.from(e['data'] as Map? ?? {});
    final sources = <Source>[];
    for (final raw in (data['items'] as List? ?? [])) {
      if (raw is! Map) continue;
      final url = '${raw['url'] ?? ''}';
      if (url.startsWith('http')) sources.add(Source('${raw['title'] ?? url}', url));
    }
    if (sources.isNotEmpty) items.add(SourcesItem(sources));
  }

  // ---- actions from the UI ------------------------------------------------

  void sendText(String text) {
    final trimmed = text.trim();
    if (trimmed.isEmpty || _core == null) return;
    items.add(UserItem(trimmed));
    mood = OrbMood.thinking;
    _core!.send({'type': 'user_message', 'text': trimmed});
    notifyListeners();
  }

  /// On the phone, speech goes through the phone's own recognizer and voice.
  bool get onPhone => !kIsWeb && Platform.isAndroid && phoneVoice;
  bool phoneVoice = true;
  bool _phoneListening = false;

  String get _speechLang => english ? 'en-IN' : 'hi-IN';

  Future<void> _listenOnPhone() async {
    if (_phoneListening) {
      await PhoneDevice.stopListening();
      return;
    }
    _phoneListening = true;
    mood = OrbMood.listening;
    notifyListeners();
    try {
      final text = await PhoneDevice.listen(_speechLang);
      mood = OrbMood.idle;
      if (text.trim().isEmpty) {
        items.add(NoticeItem(english ? 'I did not hear anything.' : 'Kuch sunai nahi diya. Dobara boliye.'));
        notifyListeners();
      } else {
        sendText(text);
      }
    } catch (e) {
      mood = OrbMood.idle;
      items.add(NoticeItem(english ? 'The phone could not listen: $e' : 'Phone sun nahi paaya: $e', error: true));
      notifyListeners();
    } finally {
      _phoneListening = false;
    }
  }

  /// Pair with the laptop's Rishu (code shown on the laptop), then connect.
  Future<void> pairLaptop(String host, int port, String code) async {
    final device = await PhoneDevice.deviceName();
    final endpoint = await pairWithLaptop(host, port, code, device);
    PairingStore(Directory(await PhoneDevice.filesDir())).save(endpoint);
    await boot();
  }

  Future<void> unpairLaptop() async {
    PairingStore(Directory(await PhoneDevice.filesDir())).clear();
    await _core?.close();
    _core = null;
    await boot();
  }

  void toggleListening() {
    if (_core == null) return;
    if (onPhone) {
      unawaited(_listenOnPhone());
      return;
    }
    if (listening) {
      _core!.send({'type': 'listen_stop'});
      return;
    }
    if (!voice.input) {
      items.add(NoticeItem(
        english
            ? 'Voice input needs a free Groq API key (Settings → AI brain). ${voice.inputReason}'
            : 'Bol kar baat karne ke liye Settings mein free Groq API key daalo. (${voice.inputReason})',
        error: true,
      ));
      notifyListeners();
      return;
    }
    _core!.send({'type': 'listen_start'});
    mood = OrbMood.listening;
    notifyListeners();
  }

  void stop() {
    _core?.send({'type': 'stop'});
    if (onPhone) unawaited(PhoneDevice.stopSpeaking());
    for (final item in items) {
      if (item is ApprovalItem && item.status == ApprovalStatus.pending) item.status = ApprovalStatus.denied;
    }
    notifyListeners();
  }

  void answer(ApprovalItem item, bool approved, {String? pin}) {
    if (item.status != ApprovalStatus.pending) return;
    item.status = approved ? ApprovalStatus.approved : ApprovalStatus.denied;
    _core?.send({
      'type': 'approval_response',
      'call_id': item.callId,
      'approved': approved,
      if (pin != null && pin.isNotEmpty) 'pin': pin,
    });
    notifyListeners();
  }

  void expire(ApprovalItem item) {
    if (item.status != ApprovalStatus.pending) return;
    item.status = ApprovalStatus.expired;
    notifyListeners();
  }

  void speak(String text) => _core?.send({'type': 'speak', 'text': text.length > 5000 ? text.substring(0, 5000) : text});

  void newConversation() {
    if (busy) return;
    _core?.send({'type': 'new_conversation'});
    items.clear();
    _streaming = null;
    notifyListeners();
  }

  // ---- teach mode ------------------------------------------------------------

  void teachDone() => sendText(english ? 'Done, I showed you. Please save it.' : 'Bas, ho gaya. Ise save kar lo.');

  void teachCancel() => _core?.send({'type': 'teach_cancel'});

  void forgetSkill(String name) => _core?.send({'type': 'forget_skill', 'name': name});

  // ---- phone link (laptop side) ------------------------------------------------

  Future<void> refreshPhoneLink() async {
    phoneLink = PhoneLinkInfo(await _req('GET', '/v1/phone'), phoneLink.code, phoneLink.codeUntil);
    notifyListeners();
  }

  Future<void> startPhoneLink() async {
    final r = await _req('POST', '/v1/phone/start');
    final seconds = (r['expires_in'] as num?)?.toInt() ?? 600;
    phoneLink = PhoneLinkInfo(r, '${r['code'] ?? ''}', DateTime.now().add(Duration(seconds: seconds)));
    notifyListeners();
  }

  Future<void> stopPhoneLink() async {
    phoneLink = PhoneLinkInfo(await _req('POST', '/v1/phone/stop'));
    notifyListeners();
  }

  Future<void> removePhone(String id) async {
    phoneLink = PhoneLinkInfo(await _req('DELETE', '/v1/phone/devices/$id'), phoneLink.code, phoneLink.codeUntil);
    notifyListeners();
  }

  // ---- offline model -----------------------------------------------------------

  Future<void> downloadLocalModel() async {
    localModel = LocalModelInfo(await _req('POST', '/v1/local-model/download'));
    notifyListeners();
  }

  Future<void> deleteLocalModel() async {
    localModel = LocalModelInfo(await _req('DELETE', '/v1/local-model'));
    notifyListeners();
  }

  Future<void> chooseLocalModel(String choice) async {
    await updateSettings({'local_model': choice});
    localModel = LocalModelInfo(await _req('GET', '/v1/local-model'));
    notifyListeners();
  }

  // ---- lock ------------------------------------------------------------------

  void unlockWithPin(String pin) {
    lockError = '';
    _core?.send({'type': 'unlock', 'method': 'pin', 'pin': pin});
    notifyListeners();
  }

  void unlockWithHello() {
    lockError = '';
    _core?.send({'type': 'unlock', 'method': 'hello'});
    notifyListeners();
  }

  void unlockWithVoice() {
    lockError = '';
    if (!voice.input) {
      lockError = english ? 'The microphone is not available. Use your PIN.' : 'Mic available nahi hai. PIN se unlock karo.';
      notifyListeners();
      return;
    }
    _core?.send({'type': 'unlock', 'method': 'voice'});
    mood = OrbMood.listening;
    notifyListeners();
  }

  void lockNow() => _core?.send({'type': 'lock'});

  void enrollPhrase() {
    _core?.send({'type': 'enroll_phrase'});
    mood = OrbMood.listening;
    notifyListeners();
  }

  Future<void> setPin(String pin, {String? current}) async {
    lock = LockInfo(await _req('PUT', '/v1/lock/pin', {'pin': pin, if (current != null) 'current': current}));
    notifyListeners();
  }

  Future<void> removePin(String current) async {
    lock = LockInfo(await _req('POST', '/v1/lock/remove', {'current': current}));
    notifyListeners();
  }

  Future<void> removePhrase() async {
    lock = LockInfo(await _req('DELETE', '/v1/lock/phrase'));
    notifyListeners();
  }

  // ---- settings, keys, activity --------------------------------------------

  Future<Map<String, dynamic>> _req(String method, String path, [Map<String, dynamic>? body]) {
    final core = _core;
    if (core == null) throw StateError('not connected');
    return core.request(method, path, body);
  }

  Future<void> updateSettings(Map<String, dynamic> patch) async {
    final result = await _req('PUT', '/v1/settings', patch);
    settings = Map<String, dynamic>.from(result['settings'] as Map? ?? settings);
    notifyListeners();
  }

  Future<void> refreshSettings() async {
    final result = await _req('GET', '/v1/settings');
    settings = Map<String, dynamic>.from(result['settings'] as Map? ?? settings);
    providers = [for (final p in (result['providers'] as List? ?? [])) Provider(Map<String, dynamic>.from(p as Map))];
    await refreshVoice();
    notifyListeners();
  }

  Future<void> refreshVoice() async {
    try {
      voice = VoiceCaps(await _req('GET', '/v1/voice'));
      notifyListeners();
    } catch (_) {}
  }

  /// Returns a code: ok, quota, auth, no_key, invalid_key, unreachable, error.
  Future<String> testKey(String provider, String key) async {
    try {
      final result = await _req('POST', '/v1/providers/$provider/test', {'api_key': key});
      return '${result['code'] ?? (result['ok'] == true ? 'ok' : 'error')}';
    } catch (_) {
      return 'error';
    }
  }

  Future<void> saveKey(String provider, String key) async {
    final result = await _req('PUT', '/v1/providers/$provider/key', {'api_key': key});
    providers = [for (final p in (result['providers'] as List? ?? [])) Provider(Map<String, dynamic>.from(p as Map))];
    await refreshVoice();
    notifyListeners();
  }

  Future<void> deleteKey(String provider) async {
    final result = await _req('DELETE', '/v1/providers/$provider/key');
    providers = [for (final p in (result['providers'] as List? ?? [])) Provider(Map<String, dynamic>.from(p as Map))];
    await refreshVoice();
    notifyListeners();
  }

  Future<List<Map<String, dynamic>>> activity() async {
    final result = await _req('GET', '/v1/activity?limit=200');
    return [for (final e in (result['entries'] as List? ?? [])) Map<String, dynamic>.from(e as Map)].reversed.toList();
  }

  void finishOnboarding({bool skipped = false}) {
    _skippedSetup = skipped || _skippedSetup;
    phase = Phase.ready;
    notifyListeners();
  }

  @visibleForTesting
  void handleEvent(Map<String, dynamic> e) => _onEvent(e);
}
