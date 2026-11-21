// Phone link (Android): talk to the laptop's Rishu over the home Wi-Fi.
//
// Pairing: the laptop shows a 6-digit code. The phone reads the laptop's TLS
// certificate, checks HMAC(code, certificate fingerprint) from /v1/phone/hello
// (a man in the middle cannot match it without the code), then sends the code
// and gets a device token. After that it pins the certificate fingerprint.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'connection.dart';

const int beaconPort = 47801;

/// Thrown when the phone has no paired laptop yet.
class NeedsPairing implements Exception {
  @override
  String toString() => 'Phone abhi kisi laptop se juda nahi hai.';
}

// ---- SHA-256 and HMAC (no packages) --------------------------------------------

const List<int> _k = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

int _rotr(int x, int n) => ((x >> n) | (x << (32 - n))) & 0xffffffff;

/// SHA-256 of [data] as 32 bytes.
Uint8List sha256(List<int> data) {
  final h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  final bitLength = data.length * 8;
  final padded = <int>[...data, 0x80];
  while (padded.length % 64 != 56) {
    padded.add(0);
  }
  for (var i = 7; i >= 0; i--) {
    padded.add((bitLength >> (i * 8)) & 0xff);
  }
  final w = List<int>.filled(64, 0);
  for (var chunk = 0; chunk < padded.length; chunk += 64) {
    for (var i = 0; i < 16; i++) {
      final j = chunk + i * 4;
      w[i] = (padded[j] << 24) | (padded[j + 1] << 16) | (padded[j + 2] << 8) | padded[j + 3];
    }
    for (var i = 16; i < 64; i++) {
      final s0 = _rotr(w[i - 15], 7) ^ _rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      final s1 = _rotr(w[i - 2], 17) ^ _rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) & 0xffffffff;
    }
    var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (var i = 0; i < 64; i++) {
      final s1 = _rotr(e, 6) ^ _rotr(e, 11) ^ _rotr(e, 25);
      final ch = (e & f) ^ ((~e & 0xffffffff) & g);
      final t1 = (hh + s1 + ch + _k[i] + w[i]) & 0xffffffff;
      final s0 = _rotr(a, 2) ^ _rotr(a, 13) ^ _rotr(a, 22);
      final maj = (a & b) ^ (a & c) ^ (b & c);
      final t2 = (s0 + maj) & 0xffffffff;
      hh = g;
      g = f;
      f = e;
      e = (d + t1) & 0xffffffff;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) & 0xffffffff;
    }
    h[0] = (h[0] + a) & 0xffffffff;
    h[1] = (h[1] + b) & 0xffffffff;
    h[2] = (h[2] + c) & 0xffffffff;
    h[3] = (h[3] + d) & 0xffffffff;
    h[4] = (h[4] + e) & 0xffffffff;
    h[5] = (h[5] + f) & 0xffffffff;
    h[6] = (h[6] + g) & 0xffffffff;
    h[7] = (h[7] + hh) & 0xffffffff;
  }
  final out = Uint8List(32);
  for (var i = 0; i < 8; i++) {
    out[i * 4] = (h[i] >> 24) & 0xff;
    out[i * 4 + 1] = (h[i] >> 16) & 0xff;
    out[i * 4 + 2] = (h[i] >> 8) & 0xff;
    out[i * 4 + 3] = h[i] & 0xff;
  }
  return out;
}

Uint8List hmacSha256(List<int> key, List<int> message) {
  var k = key.length > 64 ? sha256(key) : Uint8List.fromList(key);
  k = Uint8List.fromList([...k, ...List<int>.filled(64 - k.length, 0)]);
  final inner = sha256([for (final b in k) b ^ 0x36, ...message]);
  return sha256([for (final b in k) b ^ 0x5c, ...inner]);
}

String hex(List<int> bytes) => bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

// ---- the paired laptop -----------------------------------------------------------

class RemoteEndpoint {
  RemoteEndpoint({required this.host, required this.port, required this.token, required this.fingerprint, this.name = ''});
  final String host;
  final int port;
  final String token;
  final String fingerprint; // SHA-256 of the laptop's certificate, hex
  final String name;

  Map<String, dynamic> toJson() => {'host': host, 'port': port, 'token': token, 'fingerprint': fingerprint, 'name': name};

  static RemoteEndpoint? fromJson(Object? data) {
    if (data is! Map) return null;
    final host = data['host'], port = data['port'], token = data['token'], fp = data['fingerprint'];
    if (host is! String || port is! int || token is! String || fp is! String) return null;
    return RemoteEndpoint(host: host, port: port, token: token, fingerprint: fp, name: '${data['name'] ?? ''}');
  }
}

/// Where the pairing is kept on the phone (the app's own storage).
class PairingStore {
  PairingStore(this.folder);
  final Directory folder;

  File get _file => File('${folder.path}${Platform.pathSeparator}rishu_laptop.json');

  RemoteEndpoint? load() {
    try {
      return RemoteEndpoint.fromJson(jsonDecode(_file.readAsStringSync()));
    } catch (_) {
      return null;
    }
  }

  void save(RemoteEndpoint endpoint) {
    folder.createSync(recursive: true);
    _file.writeAsStringSync(jsonEncode(endpoint.toJson()));
  }

  void clear() {
    try {
      _file.deleteSync();
    } catch (_) {}
  }
}

HttpClient _pinnedClient(String fingerprint) {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  // The laptop's certificate is self-signed: accept it only if it is the one we paired with.
  client.badCertificateCallback = (cert, host, port) => hex(sha256(cert.der)) == fingerprint;
  return client;
}

/// Laptops that announce themselves on this Wi-Fi (UDP beacon, no secrets).
Stream<({String host, int port, String name})> discoverLaptops({Duration timeout = const Duration(seconds: 6)}) async* {
  RawDatagramSocket socket;
  try {
    socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, beaconPort, reuseAddress: true);
  } catch (_) {
    return;
  }
  final seen = <String>{};
  final controller = StreamController<({String host, int port, String name})>();
  final timer = Timer(timeout, () => controller.close());
  socket.listen((event) {
    if (event != RawSocketEvent.read) return;
    final packet = socket.receive();
    if (packet == null) return;
    try {
      final data = jsonDecode(utf8.decode(packet.data));
      if (data is Map && data['rishu'] == 1 && data['port'] is int) {
        final key = '${packet.address.address}:${data['port']}';
        if (seen.add(key) && !controller.isClosed) {
          controller.add((host: packet.address.address, port: data['port'] as int, name: '${data['name'] ?? ''}'));
        }
      }
    } catch (_) {}
  });
  yield* controller.stream;
  timer.cancel();
  socket.close();
}

/// Pair with the laptop at [host]:[port] using the code shown on the laptop.
Future<RemoteEndpoint> pairWithLaptop(String host, int port, String code, String device) async {
  String? seenFingerprint;
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  client.badCertificateCallback = (cert, h, p) {
    seenFingerprint = hex(sha256(cert.der));
    return true; // checked below with the proof before anything secret is sent
  };
  try {
    Future<Map<String, dynamic>> call(String method, String path, [Map<String, dynamic>? body]) async {
      final req = await client.openUrl(method, Uri.parse('https://$host:$port$path'));
      if (body != null) {
        req.headers.contentType = ContentType.json;
        req.add(utf8.encode(jsonEncode(body)));
      }
      final res = await req.close().timeout(const Duration(seconds: 15));
      final text = await res.transform(utf8.decoder).join();
      final decoded = text.isEmpty ? <String, dynamic>{} : jsonDecode(text);
      if (res.statusCode >= 400) {
        throw HttpException('${decoded is Map ? decoded['detail'] : 'error'} (${res.statusCode})');
      }
      return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    }

    final hello = await call('GET', '/v1/phone/hello');
    final fp = seenFingerprint;
    if (fp == null) throw const HttpException('Laptop ka certificate nahi mila.');
    if (hello['pairing'] != true) throw const HttpException('Laptop par pehle "Phone jodo" dabaiye, phir code daaliye.');
    final expected = hex(hmacSha256(utf8.encode(code.trim()), utf8.encode(fp)));
    if (hello['proof'] != expected) {
      throw const HttpException('Code match nahi hua (ya yeh Rishu wala laptop nahi hai). Laptop par dikh raha code dobara daaliye.');
    }
    final paired = await call('POST', '/v1/phone/pair', {'code': code.trim(), 'device': device});
    final token = paired['token'];
    if (token is! String) throw const HttpException('Laptop ne token nahi diya.');
    return RemoteEndpoint(host: host, port: port, token: token, fingerprint: fp, name: '${hello['name'] ?? ''}');
  } finally {
    client.close(force: true);
  }
}

/// The connection to a paired laptop: WebSocket and HTTPS with the pinned certificate.
class RemoteConnection implements CoreConnection {
  RemoteConnection._(this.endpoint, this._socket, this._http) {
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

  static Future<RemoteConnection> open(RemoteEndpoint endpoint) async {
    final http = _pinnedClient(endpoint.fingerprint);
    try {
      final socket = await WebSocket.connect(
        'wss://${endpoint.host}:${endpoint.port}/ws',
        headers: {'Authorization': 'Bearer ${endpoint.token}'},
        customClient: http,
      ).timeout(const Duration(seconds: 15));
      socket.pingInterval = const Duration(seconds: 20);
      return RemoteConnection._(endpoint, socket, http);
    } catch (e) {
      http.close(force: true);
      throw CoreStartException(
          'Laptop wale Rishu se nahi jud paaya (${endpoint.host}). Laptop on hai, Rishu khula hai, aur dono ek hi Wi-Fi par hain?');
    }
  }

  final RemoteEndpoint endpoint;
  final WebSocket _socket;
  final HttpClient _http;
  final _events = StreamController<Map<String, dynamic>>.broadcast();

  @override
  Stream<Map<String, dynamic>> get events => _events.stream;

  @override
  void send(Map<String, dynamic> event) {
    if (_socket.readyState == WebSocket.open) _socket.add(jsonEncode({'v': 1, ...event}));
  }

  @override
  Future<Map<String, dynamic>> request(String method, String path, [Map<String, dynamic>? body]) async {
    final req = await _http.openUrl(method, Uri.parse('https://${endpoint.host}:${endpoint.port}$path'));
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
  }
}
