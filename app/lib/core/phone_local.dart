// The phone's offline brain: a small model (Qwen3) run by llama.cpp's server
// on the phone itself, on 127.0.0.1. The model file is either downloaded once
// from Hugging Face (small APK) or copied once from the APK (offline APK).
// It is picked, checked (size + SHA-256) and stored like on the laptop.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'phone_core.dart' show Http;

/// The engine side (Kotlin on Android); replaced by a fake in tests.
abstract class LocalEngine {
  /// The server for this phone's CPU, or null with a reason.
  Future<({String? path, String reason})> engine();
  Future<List<String>> bundledModels();
  Future<bool> copyBundled(String name, String dest);
  Future<String?> sha256(String path);
  Future<bool> start(String model, int port, int ctx);
  Future<void> stop();
  Future<bool> running();
}

/// No offline engine (tests, or a build without it).
class NoEngine implements LocalEngine {
  @override
  Future<({String? path, String reason})> engine() async => (path: null, reason: 'no_engine');
  @override
  Future<List<String>> bundledModels() async => const [];
  @override
  Future<bool> copyBundled(String name, String dest) async => false;
  @override
  Future<String?> sha256(String path) async => null;
  @override
  Future<bool> start(String model, int port, int ctx) async => false;
  @override
  Future<void> stop() async {}
  @override
  Future<bool> running() async => false;
}

/// Streams [url] into [dest] (resuming a partial file); reports bytes done/total.
typedef Downloader = Future<void> Function(Uri url, File dest, void Function(int done, int total) progress);

Future<void> realDownload(Uri url, File dest, void Function(int done, int total) progress) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 20);
  try {
    final have = dest.existsSync() ? dest.lengthSync() : 0;
    final req = await client.getUrl(url);
    if (have > 0) req.headers.set(HttpHeaders.rangeHeader, 'bytes=$have-');
    final res = await req.close();
    if (res.statusCode != 200 && res.statusCode != 206) throw HttpException('download failed (${res.statusCode})');
    final resumed = res.statusCode == 206;
    final total = (resumed ? have : 0) + (res.contentLength > 0 ? res.contentLength : 0);
    var done = resumed ? have : 0;
    final sink = dest.openWrite(mode: resumed ? FileMode.append : FileMode.write);
    var last = DateTime.now();
    try {
      await for (final chunk in res) {
        sink.add(chunk);
        done += chunk.length;
        if (DateTime.now().difference(last).inMilliseconds > 400) {
          last = DateTime.now();
          progress(done, total);
        }
      }
    } finally {
      await sink.close();
    }
    progress(done, total);
  } finally {
    client.close(force: true);
  }
}

class PhoneLocalModel {
  PhoneLocalModel({
    required this.config,
    required this.folder,
    required this.engine,
    required this.http,
    this.download = realDownload,
    this.onChange,
    this.port = 47911,
    Duration? startWait,
  }) : startWait = startWait ?? const Duration(seconds: 120);

  final Map<String, dynamic> config; // brain.json -> local_model
  final Directory folder;
  final LocalEngine engine;
  final Http http;
  final Downloader download;
  void Function()? onChange;
  final int port;
  final Duration startWait;

  String? _server;
  String _reason = 'checking';
  List<String> _bundled = const [];
  Map<String, int>? _progress;
  String error = '';
  bool _running = false;
  Future<String?>? _starting;
  String choice = '';

  Directory get modelsDir => Directory('${folder.path}${Platform.pathSeparator}models');
  Map<String, dynamic> get _choices => Map<String, dynamic>.from(config['choices'] as Map? ?? const {});
  Map<String, dynamic> get _spec =>
      Map<String, dynamic>.from(_choices[choice] as Map? ?? _choices[config['default']] as Map? ?? const {});
  bool get engineOk => _server != null;
  bool get busy => _progress != null;

  Future<void> init({bool warm = false}) async {
    if (choice.isEmpty || !_choices.containsKey(choice)) choice = '${config['default'] ?? 'small'}';
    final found = await engine.engine();
    _server = found.path;
    _reason = found.reason;
    _bundled = await engine.bundledModels();
    _changed();
    if (_bundled.isNotEmpty && modelFile() == null) {
      unawaited(prepareBundled());
    } else if (warm && modelFile() != null) {
      unawaited(ensure());
    }
  }

  void _changed() => onChange?.call();

  /// The quantisations in order of preference (like rishu_core.llm.local.quant_order).
  List<String> _quants() {
    final first = '${_spec['file_suffix'] ?? ''}'.replaceAll(RegExp(r'\.gguf$'), '');
    return [if (first.isNotEmpty) first, for (final q in (config['quants'] as List? ?? const [])) '$q'];
  }

  String? pick(List<String> names) {
    final files = [
      for (final n in names)
        if (n.toLowerCase().endsWith('.gguf') && !n.toLowerCase().contains('mmproj')) n
    ];
    for (final quant in _quants()) {
      for (final name in files) {
        if (name.toLowerCase().replaceAll(RegExp(r'\.gguf$'), '').endsWith(quant.toLowerCase())) return name;
      }
    }
    return null;
  }

  String get _prefix => '${_spec['repo'] ?? ''}'.split('/').last.replaceAll(RegExp(r'-GGUF$'), '').toLowerCase();

  File? modelFile() {
    if (!modelsDir.existsSync()) return null;
    final names = [
      for (final f in modelsDir.listSync().whereType<File>())
        if (f.uri.pathSegments.last.toLowerCase().startsWith(_prefix)) f.uri.pathSegments.last
    ];
    final name = pick(names);
    return name == null ? null : File('${modelsDir.path}${Platform.pathSeparator}$name');
  }

  Map<String, dynamic> status() => {
        'engine': engineOk,
        'engine_reason': _reason,
        'choice': choice,
        'choices': {for (final e in _choices.entries) e.key: '${(e.value as Map)['label'] ?? e.key}'},
        'downloaded': modelFile() != null,
        'size_mb': (_spec['size_mb'] as num?)?.toInt() ?? 0,
        'running': _running,
        'bundled': _bundled.isNotEmpty,
        if (_progress != null) 'progress': Map<String, int>.from(_progress!),
        'error': error,
      };

  void _setProgress(int done, int total) {
    _progress = {'done': done, 'total': total};
    _changed();
  }

  /// Offline APK: copy the model out of the APK once (llama.cpp needs a real file).
  Future<void> prepareBundled() async {
    if (busy || _bundled.isEmpty) return;
    final name = pick(_bundled) ?? _bundled.first;
    final dest = File('${modelsDir.path}${Platform.pathSeparator}$name');
    final part = File('${dest.path}.part');
    error = '';
    _setProgress(0, ((_spec['size_mb'] as num?)?.toInt() ?? 0) * 1024 * 1024);
    final watch = Timer.periodic(const Duration(milliseconds: 500), (_) {
      if (part.existsSync()) _setProgress(part.lengthSync(), _progress?['total'] ?? 0);
    });
    try {
      modelsDir.createSync(recursive: true);
      if (!await engine.copyBundled(name, part.path)) throw const FileSystemException('copy failed');
      part.renameSync(dest.path);
    } catch (e) {
      error = 'Offline dimaag taiyaar nahi ho paaya: $e (phone mein ~500 MB jagah chahiye)';
      if (part.existsSync()) part.deleteSync();
    } finally {
      watch.cancel();
      _progress = null;
      _changed();
    }
  }

  /// Small APK: download the chosen model once (Wi-Fi recommended), then check it.
  Future<void> downloadModel() async {
    if (busy) return;
    if (_bundled.isNotEmpty && choice == '${config['default']}') return prepareBundled();
    error = '';
    _setProgress(0, ((_spec['size_mb'] as num?)?.toInt() ?? 0) * 1024 * 1024);
    try {
      final repo = '${_spec['repo']}';
      final (status, text) = await http('GET', Uri.parse('https://huggingface.co/api/models/$repo?blobs=true'), const {}, null);
      if (status != 200) throw HttpException('Hugging Face answered $status');
      final siblings = [
        for (final s in ((jsonDecode(text) as Map)['siblings'] as List? ?? const []))
          if (s is Map) Map<String, dynamic>.from(s)
      ];
      final name = pick([for (final s in siblings) '${s['rfilename'] ?? ''}']);
      if (name == null) throw StateError('no usable .gguf file in $repo');
      final sibling = siblings.firstWhere((s) => s['rfilename'] == name);
      final lfs = Map<String, dynamic>.from(sibling['lfs'] as Map? ?? const {});
      final size = ((lfs['size'] ?? sibling['size'] ?? 0) as num).toInt();
      final sha = '${lfs['sha256'] ?? ''}';
      modelsDir.createSync(recursive: true);
      final part = File('${modelsDir.path}${Platform.pathSeparator}$name.part');
      await download(Uri.parse('https://huggingface.co/$repo/resolve/main/$name'), part,
          (done, total) => _setProgress(done, total > 0 ? total : size));
      if (size > 0 && part.lengthSync() != size) throw StateError('the download is incomplete; tap Download again to resume');
      if (sha.isNotEmpty && (await engine.sha256(part.path))?.toLowerCase() != sha.toLowerCase()) {
        part.deleteSync();
        throw StateError('the downloaded file is damaged; please download again');
      }
      part.renameSync('${modelsDir.path}${Platform.pathSeparator}$name');
    } catch (e) {
      error = 'Download nahi hua: $e';
    } finally {
      _progress = null;
      _changed();
    }
  }

  Future<void> delete() async {
    await stop();
    if (modelsDir.existsSync()) {
      for (final f in modelsDir.listSync().whereType<File>()) {
        if (f.path.toLowerCase().contains(_prefix)) f.deleteSync();
      }
    }
    _changed();
  }

  Future<void> stop() async {
    _starting = null;
    if (_running) await engine.stop();
    _running = false;
  }

  /// The local server's base URL, starting it when needed; null when it cannot run.
  Future<String?> ensure() {
    return _starting ??= _start().whenComplete(() => _starting = null);
  }

  Future<String?> _start() async {
    final base = 'http://127.0.0.1:$port/v1';
    if (_running && await engine.running()) return base;
    final model = modelFile();
    if (!engineOk || model == null || busy) return null;
    if (!await engine.start(model.path, port, ((config['ctx_size'] as num?) ?? 6144).toInt())) {
      error = 'Offline dimaag start nahi hua.';
      _changed();
      return null;
    }
    final until = DateTime.now().add(startWait);
    while (DateTime.now().isBefore(until)) {
      try {
        final (status, _) = await http('GET', Uri.parse('http://127.0.0.1:$port/health'), const {}, null);
        if (status == 200) {
          _running = true;
          error = '';
          _changed();
          return base;
        }
      } catch (_) {
        // still loading
      }
      if (!await engine.running()) break;
      await Future<void>.delayed(const Duration(milliseconds: 500));
    }
    await engine.stop();
    error = 'Offline dimaag load nahi hua (phone ki RAM kam ho sakti hai).';
    _changed();
    return null;
  }

  /// Usable now or after a start: engine for this phone and a model file.
  bool get usable => engineOk && modelFile() != null && !busy;
}
