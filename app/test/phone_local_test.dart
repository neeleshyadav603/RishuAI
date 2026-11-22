// The phone's offline brain: picking, downloading, checking, copying from the
// offline APK, starting the server, and being used when there is no key or internet.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:rishu/core/phone_core.dart';
import 'package:rishu/core/phone_local.dart';

import 'phone_core_test.dart' show FakeActions, FakeSecrets;

const localConfig = {
  'default': 'small',
  'ctx_size': 4096,
  'quants': ['Q4_K_M', 'Q4_0', 'Q8_0'],
  'choices': {
    'small': {'label': 'Chhota', 'repo': 'ggml-org/Qwen3-0.6B-GGUF', 'file_suffix': 'Q4_K_M.gguf', 'size_mb': 1},
    'better': {'label': 'Behtar', 'repo': 'ggml-org/Qwen3-1.7B-GGUF', 'file_suffix': 'Q4_K_M.gguf', 'size_mb': 2},
  },
};

final modelBytes = utf8.encode('GGUF model bytes');

class FakeEngine implements LocalEngine {
  FakeEngine({this.bundled = const [], this.path = '/lib/libllama_server.so', this.sha = 'abc123'});
  final List<String> bundled;
  final String? path;
  final String sha;
  bool isRunning = false;
  final List<String> started = [];

  @override
  Future<({String? path, String reason})> engine() async => (path: path, reason: path == null ? 'no_engine' : '');
  @override
  Future<List<String>> bundledModels() async => bundled;
  @override
  Future<bool> copyBundled(String name, String dest) async {
    File(dest).writeAsBytesSync(modelBytes);
    return true;
  }

  @override
  Future<String?> sha256(String path) async => sha;
  @override
  Future<bool> start(String model, int port, int ctx) async {
    started.add('$model $port $ctx');
    isRunning = true;
    return true;
  }

  @override
  Future<void> stop() async => isRunning = false;
  @override
  Future<bool> running() async => isRunning;
}

/// Hugging Face, the local server and (failing) online providers.
class FakeNet {
  FakeNet({this.online = true});
  bool online;
  final List<String> chats = [];

  Future<(int, String)> call(String method, Uri url, Map<String, String> headers, String? body) async {
    if (url.host == 'huggingface.co') {
      return (
        200,
        jsonEncode({
          'siblings': [
            {'rfilename': 'Qwen3-0.6B-f16.gguf'},
            {'rfilename': 'Qwen3-0.6B-Q4_0.gguf', 'lfs': {'size': modelBytes.length, 'sha256': 'ABC123'}},
          ],
        })
      );
    }
    if (url.host == '127.0.0.1') {
      if (url.path == '/health') return (200, '{"status":"ok"}');
      chats.add('local');
      return (200, jsonEncode({'choices': [{'message': {'content': 'Main offline hoon, phir bhi madad karti hoon!'}}]}));
    }
    chats.add(url.host);
    if (!online) throw const SocketException('no internet');
    return (500, '{}');
  }
}

Future<void> fakeDownload(Uri url, File dest, void Function(int, int) progress) async {
  expect(url.toString(), 'https://huggingface.co/ggml-org/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_0.gguf');
  progress(4, modelBytes.length);
  dest.writeAsBytesSync(modelBytes);
  progress(modelBytes.length, modelBytes.length);
}

void main() {
  late Directory folder;
  setUp(() => folder = Directory.systemTemp.createTempSync('rishu_local_'));
  tearDown(() => folder.deleteSync(recursive: true));

  PhoneLocalModel model(FakeEngine engine, FakeNet net, {Downloader download = fakeDownload}) => PhoneLocalModel(
        config: localConfig,
        folder: folder,
        engine: engine,
        http: net.call,
        download: download,
        startWait: const Duration(seconds: 2),
      );

  test('the preferred file the repo has is downloaded, checked and kept', () async {
    final engine = FakeEngine();
    final local = model(engine, FakeNet());
    final seen = <Map<String, dynamic>>[];
    local.onChange = () => seen.add(local.status());
    await local.init();
    expect(local.status()['downloaded'], isFalse);
    expect(local.status()['engine'], isTrue);
    await local.downloadModel();
    expect(local.error, isEmpty);
    expect(local.modelFile()!.path, endsWith('Qwen3-0.6B-Q4_0.gguf'));
    expect(seen.any((s) => s['progress'] is Map), isTrue);
    expect(local.status()['downloaded'], isTrue);
    expect(local.status().containsKey('progress'), isFalse);
  });

  test('a damaged download is thrown away', () async {
    final local = model(FakeEngine(sha: 'other'), FakeNet());
    await local.init();
    await local.downloadModel();
    expect(local.error, contains('damaged'));
    expect(local.modelFile(), isNull);
    expect(Directory('${folder.path}/models').listSync(), isEmpty);
  });

  test('the offline APK copies its model out once by itself', () async {
    final engine = FakeEngine(bundled: ['Qwen3-0.6B-Q4_0.gguf']);
    final local = model(engine, FakeNet());
    await local.init();
    for (var i = 0; i < 50 && local.modelFile() == null; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    expect(local.modelFile(), isNotNull);
    expect(local.status()['bundled'], isTrue);
  });

  test('a phone without the engine says so and never starts', () async {
    final local = model(FakeEngine(path: null), FakeNet());
    await local.init();
    expect(local.status()['engine'], isFalse);
    expect(await local.ensure(), isNull);
  });

  test('the server starts once and is reused; delete stops it and frees the space', () async {
    final engine = FakeEngine();
    final local = model(engine, FakeNet());
    await local.init();
    await local.downloadModel();
    final urls = await Future.wait([local.ensure(), local.ensure()]);
    expect(urls, ['http://127.0.0.1:47911/v1', 'http://127.0.0.1:47911/v1']);
    expect(engine.started.single, endsWith('Q4_0.gguf 47911 4096'));
    await local.delete();
    expect(engine.isRunning, isFalse);
    expect(local.modelFile(), isNull);
  });

  group('phone brain', () {
    PhoneCore core(FakeSecrets secrets, FakeEngine engine, FakeNet net) => PhoneCore(
          brain: {
            'order': ['groq'],
            'providers': {
              'groq': {'label': 'Groq', 'base_url': 'https://groq.test/v1', 'models': {'smart': ['m1']}},
            },
            'prompts': {'persona': 'You are Rishu.', 'personas': {}, 'rules': 'Phone rules.'},
            'local_model': localConfig,
          },
          folder: folder,
          secrets: secrets,
          actions: FakeActions(),
          http: net.call,
          engine: engine,
          downloader: fakeDownload,
        );

    Future<Map<String, dynamic>> reply(PhoneCore c) async {
      final done = Completer<Map<String, dynamic>>();
      final sub = c.events.listen((e) {
        if ((e['type'] == 'assistant_message' || e['type'] == 'error') && !done.isCompleted) done.complete(e);
      });
      await Future<void>.delayed(const Duration(milliseconds: 50));
      c.send({'type': 'user_message', 'text': 'namaste'});
      final e = await done.future.timeout(const Duration(seconds: 5));
      await sub.cancel();
      return e;
    }

    test('without a key it answers with the offline model', () async {
      final engine = FakeEngine();
      final net = FakeNet();
      final c = core(FakeSecrets(), engine, net);
      await c.request('POST', '/v1/local-model/download');
      for (var i = 0; i < 50 && !(await c.request('GET', '/v1/local-model'))['downloaded']; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      final e = await reply(c);
      expect(e['provider'], 'rishu_local');
      expect(e['text'], contains('offline'));
      expect(net.chats, ['local']);
    });

    test('without internet it falls back from Groq to the offline model', () async {
      final secrets = FakeSecrets()..data['key_groq'] = 'gsk-test';
      final net = FakeNet(online: false);
      final c = core(secrets, FakeEngine(bundled: ['Qwen3-0.6B-Q4_0.gguf']), net);
      await Future<void>.delayed(const Duration(milliseconds: 200));
      final e = await reply(c);
      expect(e['provider'], 'rishu_local');
      expect(net.chats, ['groq.test', 'local']);
    });

    test('nothing ready: the error says how to get a brain', () async {
      final e = await reply(core(FakeSecrets(), FakeEngine(), FakeNet()));
      expect(e['type'], 'error');
      expect(e['message'], contains('Offline dimaag'));
    });
  });
}
