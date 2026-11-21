// The phone's own brain: protocol events, keys, fallback and phone tools,
// with a fake HTTP layer (no network) and fake Android actions.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:rishu/core/phone_core.dart';

class FakeSecrets implements SecretStore {
  final Map<String, String> data = {};
  @override
  Future<String?> read(String name) async => data[name];
  @override
  Future<void> save(String name, String value) async => data[name] = value;
  @override
  Future<void> delete(String name) async => data.remove(name);
}

class FakeActions implements PhoneActions {
  final List<String> done = [];
  @override
  Future<bool> setAlarm(int hour, int minute, String label) async {
    done.add('alarm $hour:$minute $label');
    return true;
  }

  @override
  Future<bool> setTimer(int seconds, String label) async {
    done.add('timer $seconds');
    return true;
  }

  @override
  Future<bool> openUrl(String url) async {
    done.add('url $url');
    return true;
  }

  @override
  Future<bool> dial(String number) async {
    done.add('dial $number');
    return true;
  }

  @override
  Future<List<Map<String, String>>> apps() async => [
        {'label': 'YouTube', 'package': 'com.google.android.youtube'},
        {'label': 'WhatsApp', 'package': 'com.whatsapp'},
      ];

  @override
  Future<bool> openApp(String package) async {
    done.add('app $package');
    return true;
  }

  @override
  Future<List<Map<String, String>>> findContact(String name) async => [
        {'name': 'Test Contact', 'number': '+91 90000 00000'},
      ];
}

const brain = {
  'order': ['groq', 'gemini'],
  'providers': {
    'groq': {
      'label': 'Groq',
      'key_url': 'https://console.groq.com/keys',
      'base_url': 'https://groq.test/v1',
      'models': {'smart': ['big-model'], 'fast': ['small-model']},
    },
    'gemini': {
      'label': 'Gemini',
      'key_url': 'https://aistudio.google.com/apikey',
      'base_url': 'https://gemini.test/v1',
      'models': {'smart': ['gem-model']},
    },
  },
  'prompts': {
    'persona': 'You are Rishu.',
    'personas': {'professional': 'Be professional.', 'personal': 'Be warm.'},
    'rules': 'Phone rules.',
  },
};

/// Answers chat calls from a script; records every request.
class FakeHttp {
  FakeHttp(this.script);
  final List<Object> script; // each: a reply map, or an int status code
  final List<(String, Uri, String?)> calls = [];

  Future<(int, String)> call(String method, Uri url, Map<String, String> headers, String? body) async {
    calls.add((method, url, body));
    if (url.path.endsWith('/models')) return (headers['Authorization'] == 'Bearer good' ? 200 : 401, '{"data": []}');
    final next = script.removeAt(0);
    if (next is int) return (next, '{"error": "x"}');
    return (200, jsonEncode({'choices': [{'message': next}]}));
  }
}

Map<String, Object?> toolCall(String id, String name, Map<String, Object> args) => {
      'content': null,
      'tool_calls': [
        {'id': id, 'type': 'function', 'function': {'name': name, 'arguments': jsonEncode(args)}},
      ],
    };

void main() {
  late Directory folder;
  late FakeSecrets secrets;
  late FakeActions actions;
  // The core's stream can be listened to once; tests listen many times.
  late Stream<Map<String, dynamic>> events;

  setUp(() {
    folder = Directory.systemTemp.createTempSync('rishu_phone_');
    secrets = FakeSecrets();
    actions = FakeActions();
  });

  tearDown(() => folder.deleteSync(recursive: true));

  PhoneCore make(FakeHttp http) {
    final core = PhoneCore(
      brain: brain,
      folder: folder,
      secrets: secrets,
      actions: actions,
      http: http.call,
      now: () => DateTime(2026, 11, 21, 9, 30),
    );
    events = core.events.asBroadcastStream();
    return core;
  }

  Future<List<Map<String, dynamic>>> until(PhoneCore core, bool Function(Map<String, dynamic>) done, [void Function()? start]) async {
    final seen = <Map<String, dynamic>>[];
    final finished = Completer<void>();
    final sub = events.listen((e) {
      seen.add(e);
      if (!finished.isCompleted && done(e)) finished.complete();
    });
    start?.call();
    await finished.future.timeout(const Duration(seconds: 5));
    await sub.cancel();
    return seen;
  }

  test('hello says phone, lists providers without keys', () async {
    final core = make(FakeHttp([]));
    final seen = <Map<String, dynamic>>[];
    final sub = events.listen(seen.add);
    await Future<void>.delayed(const Duration(milliseconds: 50));
    final hello = seen.firstWhere((e) => e['type'] == 'hello');
    expect(hello['version'], 'phone');
    expect([for (final p in hello['providers'] as List) p['name']], ['groq', 'gemini']);
    expect((hello['providers'] as List).every((p) => p['configured'] == false), isTrue);
    await sub.cancel();
  });

  test('keys are tested, saved in the secret store and listed as configured', () async {
    final core = make(FakeHttp([]));
    expect((await core.request('POST', '/v1/providers/groq/test', {'api_key': 'good'}))['code'], 'ok');
    expect((await core.request('POST', '/v1/providers/groq/test', {'api_key': 'bad'}))['code'], 'invalid');
    final saved = await core.request('PUT', '/v1/providers/groq/key', {'api_key': ' good '});
    expect(secrets.data['key_groq'], 'good');
    expect((saved['providers'] as List).first['configured'], isTrue);
    await core.request('DELETE', '/v1/providers/groq/key');
    expect(secrets.data.containsKey('key_groq'), isFalse);
  });

  test('settings are kept in the phone folder', () async {
    final core = make(FakeHttp([]));
    await core.request('PUT', '/v1/settings', {'user_name': 'Neel', 'unknown': 1});
    final again = make(FakeHttp([]));
    expect((await again.request('GET', '/v1/settings'))['settings']['user_name'], 'Neel');
    expect(core.settings.containsKey('unknown'), isFalse);
  });

  test('without a key the user is told to add a Groq key', () async {
    final core = make(FakeHttp([]));
    final seen = await until(core, (e) => e['type'] == 'error', () => core.send({'type': 'user_message', 'text': 'hi'}));
    expect(seen.last['code'], 'no_brain');
  });

  test('a plain reply, falling back to the next model and provider', () async {
    secrets.data['key_groq'] = 'good';
    secrets.data['key_gemini'] = 'good';
    final http = FakeHttp([429, 500, {'content': 'Namaste!'}]);
    final core = make(http);
    final seen = await until(core, (e) => e['type'] == 'assistant_message', () => core.send({'type': 'user_message', 'text': 'hi'}));
    expect(seen.last['text'], 'Namaste!');
    expect(seen.last['provider'], 'gemini');
    final chats = http.calls.where((c) => c.$2.path.endsWith('/chat/completions')).toList();
    expect(chats.length, 3);
    final body = jsonDecode(chats.first.$3!) as Map;
    expect(body['model'], 'big-model');
    expect((body['messages'] as List).first['content'], contains('Phone rules.'));
    expect((body['tools'] as List).map((t) => t['function']['name']), containsAll(['set_alarm', 'whatsapp_message', 'web_search']));
  });

  test('an alarm runs at once and Rishu replies', () async {
    secrets.data['key_groq'] = 'good';
    final core = make(FakeHttp([
      toolCall('c1', 'set_alarm', {'time': '06:30', 'label': 'Uth jao'}),
      {'content': 'Alarm 6:30 ka laga diya.'},
    ]));
    final seen = await until(core, (e) => e['type'] == 'assistant_message', () => core.send({'type': 'user_message', 'text': 'alarm'}));
    expect(actions.done, ['alarm 6:30 Uth jao']);
    expect(seen.any((e) => e['type'] == 'tool_result' && e['ok'] == true), isTrue);
    expect(seen.any((e) => e['type'] == 'tool_call_proposed'), isFalse);
  });

  test('a WhatsApp message waits for approval and only opens the chat', () async {
    secrets.data['key_groq'] = 'good';
    final core = make(FakeHttp([
      toolCall('w1', 'whatsapp_message', {'number': '9000000000', 'text': 'Aaj nahi aa paunga'}),
      {'content': 'WhatsApp khol diya, Send aap dabao.'},
    ]));
    final done = Completer<void>();
    final sub = events.listen((e) {
      if (e['type'] == 'tool_call_proposed') {
        expect(actions.done, isEmpty);
        core.send({'type': 'approval_response', 'call_id': e['call_id'], 'approved': true});
      }
      if (e['type'] == 'assistant_message' && !done.isCompleted) done.complete();
    });
    core.send({'type': 'user_message', 'text': 'msg'});
    await done.future.timeout(const Duration(seconds: 5));
    await sub.cancel();
    expect(actions.done.single, startsWith('url https://wa.me/919000000000?text='));
  });

  test('a denied call is not run', () async {
    secrets.data['key_groq'] = 'good';
    final core = make(FakeHttp([
      toolCall('d1', 'dial', {'number': '100'}),
      {'content': 'Theek hai, call nahi kiya.'},
    ]));
    final sub = events.listen((e) {
      if (e['type'] == 'tool_call_proposed') core.send({'type': 'approval_response', 'call_id': e['call_id'], 'approved': false});
    });
    await Future<void>.delayed(const Duration(milliseconds: 10));
    core.send({'type': 'user_message', 'text': 'call'});
    await Future<void>.delayed(const Duration(milliseconds: 300));
    await sub.cancel();
    expect(actions.done, isEmpty);
  });

  test('memories are kept on the phone and put in the prompt', () async {
    secrets.data['key_groq'] = 'good';
    final http = FakeHttp([
      toolCall('m1', 'remember', {'fact': 'Lecture 10 baje hai'}),
      {'content': 'Yaad rakh liya.'},
      {'content': 'Lecture 10 baje.'},
    ]);
    final core = make(http);
    await until(core, (e) => e['type'] == 'assistant_message', () => core.send({'type': 'user_message', 'text': 'yaad rakho'}));
    await until(core, (e) => e['type'] == 'assistant_message', () => core.send({'type': 'user_message', 'text': 'kab?'}));
    final last = jsonDecode(http.calls.last.$3!) as Map;
    expect((last['messages'] as List).first['content'], contains('Lecture 10 baje hai'));
    expect(File('${folder.path}/memories.json').existsSync(), isTrue);
  });

  test('laptop-only endpoints say so', () async {
    final core = make(FakeHttp([]));
    await expectLater(core.request('POST', '/v1/lock/pin'), throwsA(isA<HttpException>()));
  });
}
