// Talking to the Rishu core: start the bundled core process, then speak the
// JSON event protocol over a local WebSocket (see shared/protocol).
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

/// Everything the app needs from the core. A fake implements it in tests.
abstract class CoreConnection {
  Stream<Map<String, dynamic>> get events;
  void send(Map<String, dynamic> event);
  Future<Map<String, dynamic>> request(String method, String path, [Map<String, dynamic>? body]);
  Future<void> close();
}

class CoreStartException implements Exception {
  CoreStartException(this.message);
  final String message;
  @override
  String toString() => message;
}

class CoreEndpoint {
  CoreEndpoint(this.port, this.token, [this.process]);
  final int port;
  final String token;
  final Process? process;
}

/// Starts `core\rishu-core.exe` next to the app and waits until it is ready.
class CoreLauncher {
  static String _token() {
    final random = Random.secure();
    final bytes = List<int>.generate(32, (_) => random.nextInt(256));
    return base64Url.encode(bytes).replaceAll('=', '');
  }

  static String? findCore() {
    final env = Platform.environment;
    final override = env['RISHU_CORE_EXE'];
    if (override != null && File(override).existsSync()) return override;
    final dir = File(Platform.resolvedExecutable).parent.path;
    final sep = Platform.pathSeparator;
    for (final name in ['rishu-core.exe', 'rishu-core']) {
      final path = '$dir${sep}core$sep$name';
      if (File(path).existsSync()) return path;
    }
    return null;
  }

  static Future<CoreEndpoint> start({Duration timeout = const Duration(seconds: 90)}) async {
    final env = Platform.environment;
    // Development: connect to a core that is already running.
    final devPort = int.tryParse(env['RISHU_CORE_PORT'] ?? '');
    final devToken = env['RISHU_TOKEN'];
    if (devPort != null && devToken != null) return CoreEndpoint(devPort, devToken);

    final exe = findCore();
    if (exe == null) {
      throw CoreStartException('Rishu ka core nahi mila (core\\rishu-core.exe). Rishu ko dobara install karo.');
    }
    final token = _token();
    final readyFile = File(
      '${Directory.systemTemp.path}${Platform.pathSeparator}rishu-ready-$pid-${DateTime.now().millisecondsSinceEpoch}.txt',
    );
    final Process process;
    try {
      process = await Process.start(
        exe,
        ['--serve', '--exit-with-parent'],
        workingDirectory: File(exe).parent.path,
        environment: {
          'RISHU_TOKEN': token,
          'RISHU_READY_FILE': readyFile.path,
          'RISHU_PARENT_PID': '$pid',
          'PYTHONIOENCODING': 'utf-8',
        },
      );
    } on ProcessException catch (e) {
      throw CoreStartException('Rishu ka core start nahi ho paaya: ${e.message}');
    }

    final ready = Completer<int>();
    final errorLines = <String>[];
    void readyLine(String line) {
      const prefix = 'RISHU_READY ';
      if (!line.startsWith(prefix) || ready.isCompleted) return;
      try {
        final info = jsonDecode(line.substring(prefix.length)) as Map<String, dynamic>;
        ready.complete(info['port'] as int);
      } catch (_) {}
    }

    // Always drain both pipes so the core never blocks on a full buffer.
    process.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen(readyLine, onError: (_) {});
    process.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      errorLines.add(line);
      if (errorLines.length > 20) errorLines.removeAt(0);
    }, onError: (_) {});
    unawaited(process.exitCode.then((code) {
      if (!ready.isCompleted) {
        final tail = errorLines.isEmpty ? '' : '\n${errorLines.take(6).join('\n')}';
        ready.completeError(CoreStartException('Rishu ka core band ho gaya (code $code).$tail'));
      }
    }));
    final poll = Timer.periodic(const Duration(milliseconds: 250), (_) {
      if (ready.isCompleted) return;
      try {
        if (readyFile.existsSync()) readyLine(readyFile.readAsStringSync().trim());
      } catch (_) {}
    });
    try {
      final port = await ready.future.timeout(timeout, onTimeout: () {
        process.kill();
        throw CoreStartException('Rishu ka core time par start nahi hua. Antivirus scan chal raha ho to thodi der baad dobara kholo.');
      });
      return CoreEndpoint(port, token, process);
    } finally {
      poll.cancel();
      try {
        if (readyFile.existsSync()) readyFile.deleteSync();
      } catch (_) {}
    }
  }
}

/// The real connection: WebSocket for events, HTTP for settings and keys.
class WebSocketConnection implements CoreConnection {
  WebSocketConnection._(this.endpoint, this._socket) {
    _socket.listen(
      (data) {
        if (data is! String) return;
        try {
          final event = jsonDecode(data);
          if (event is Map<String, dynamic>) _events.add(event);
        } catch (_) {}
      },
      onDone: () => _events.close(),
      onError: (Object e) => _events.close(),
      cancelOnError: true,
    );
  }

  static Future<WebSocketConnection> open(CoreEndpoint endpoint) async {
    final socket = await WebSocket.connect(
      'ws://127.0.0.1:${endpoint.port}/ws',
      headers: {'Authorization': 'Bearer ${endpoint.token}'},
    ).timeout(const Duration(seconds: 15));
    socket.pingInterval = const Duration(seconds: 20);
    return WebSocketConnection._(endpoint, socket);
  }

  final CoreEndpoint endpoint;
  final WebSocket _socket;
  final _events = StreamController<Map<String, dynamic>>.broadcast();
  final _http = HttpClient()..connectionTimeout = const Duration(seconds: 10);

  @override
  Stream<Map<String, dynamic>> get events => _events.stream;

  @override
  void send(Map<String, dynamic> event) {
    if (_socket.readyState == WebSocket.open) {
      _socket.add(jsonEncode({'v': 1, ...event}));
    }
  }

  @override
  Future<Map<String, dynamic>> request(String method, String path, [Map<String, dynamic>? body]) async {
    final uri = Uri.parse('http://127.0.0.1:${endpoint.port}$path');
    final req = await _http.openUrl(method, uri);
    req.headers.set('Authorization', 'Bearer ${endpoint.token}');
    if (body != null) {
      req.headers.contentType = ContentType.json;
      req.add(utf8.encode(jsonEncode(body)));
    }
    final res = await req.close().timeout(const Duration(seconds: 30));
    final text = await res.transform(utf8.decoder).join();
    final decoded = text.isEmpty ? <String, dynamic>{} : jsonDecode(text);
    if (res.statusCode >= 400) {
      final detail = decoded is Map ? decoded['detail'] : null;
      throw HttpException('${detail ?? 'Request failed'} (${res.statusCode})');
    }
    return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
  }

  @override
  Future<void> close() async {
    await _socket.close();
    _http.close(force: true);
    endpoint.process?.kill();
  }
}

/// Open a web page in the user's default browser.
Future<void> openInBrowser(String url) async {
  final uri = Uri.tryParse(url);
  if (uri == null || !(uri.scheme == 'http' || uri.scheme == 'https')) return;
  try {
    if (Platform.isWindows) {
      await Process.run('rundll32', ['url.dll,FileProtocolHandler', uri.toString()]);
    } else if (Platform.isMacOS) {
      await Process.run('open', [uri.toString()]);
    } else if (Platform.isLinux) {
      await Process.run('xdg-open', [uri.toString()]);
    }
  } catch (_) {}
}
