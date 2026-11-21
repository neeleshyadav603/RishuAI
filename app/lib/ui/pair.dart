// Android: pair the phone with the laptop's Rishu (same Wi-Fi, 6-digit code).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/device.dart';
import '../core/remote.dart';
import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'orb.dart';
import 'theme.dart';

class PairScreen extends StatefulWidget {
  const PairScreen({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<PairScreen> createState() => _PairScreenState();
}

class _PairScreenState extends State<PairScreen> {
  final _host = TextEditingController();
  final _code = TextEditingController();
  final _found = <({String host, int port, String name})>[];
  StreamSubscription<({String host, int port, String name})>? _scan;
  int _port = 47800;
  bool _busy = false;
  bool _scanning = false;
  String _error = '';

  AssistantController get c => widget.controller;

  @override
  void initState() {
    super.initState();
    _find();
  }

  Future<void> _find() async {
    await _scan?.cancel();
    setState(() {
      _scanning = true;
      _found.clear();
    });
    await PhoneDevice.multicast(true);
    _scan = discoverLaptops(timeout: const Duration(seconds: 8)).listen(
      (laptop) => setState(() {
        _found.add(laptop);
        if (_host.text.isEmpty) {
          _host.text = laptop.host;
          _port = laptop.port;
        }
      }),
      onDone: () {
        PhoneDevice.multicast(false);
        if (mounted) setState(() => _scanning = false);
      },
    );
  }

  @override
  void dispose() {
    _scan?.cancel();
    _host.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _pair() async {
    final host = _host.text.trim();
    final code = _code.text.trim();
    if (host.isEmpty || code.length != 6) {
      setState(() => _error = tr(c, 'Laptop ka address aur 6 ank ka code daaliye.', 'Enter the laptop address and the 6-digit code.'));
      return;
    }
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await c.pairLaptop(host, _port, code);
    } catch (e) {
      if (mounted) setState(() => _error = '$e'.replaceFirst('HttpException: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    const muted = TextStyle(color: RishuColors.muted, fontSize: 13.5);
    return Scaffold(
      backgroundColor: RishuColors.background,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Center(child: Orb(mood: OrbMood.idle, level: 0, size: 120)),
                  const SizedBox(height: 16),
                  Text(
                    tr(c, 'Phone ko laptop wale Rishu se jodo', 'Connect this phone to Rishu on your laptop'),
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: RishuColors.text),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    tr(c, 'Laptop par Rishu kholo → Settings → "Phone se jodo" → code dikhega. Phone aur laptop ek hi Wi-Fi par hon.',
                        'On the laptop: Rishu → Settings → "Connect phone" shows a code. Both must be on the same Wi-Fi.'),
                    textAlign: TextAlign.center,
                    style: muted,
                  ),
                  const SizedBox(height: 18),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          _scanning
                              ? tr(c, 'Laptop dhoondh rahi hoon…', 'Looking for the laptop…')
                              : _found.isEmpty
                                  ? tr(c, 'Koi laptop nahi mila, address khud daaliye', 'No laptop found; type its address')
                                  : tr(c, '${_found.length} laptop mila', '${_found.length} found'),
                          style: muted,
                        ),
                      ),
                      TextButton.icon(
                        onPressed: _scanning ? null : _find,
                        icon: const Icon(Icons.wifi_find_rounded),
                        label: Text(tr(c, 'Phir dhoondho', 'Search again')),
                      ),
                    ],
                  ),
                  for (final laptop in _found)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.laptop_windows_rounded, color: RishuColors.cyan),
                      title: Text(laptop.name.isEmpty ? laptop.host : laptop.name, style: const TextStyle(color: RishuColors.text)),
                      subtitle: Text('${laptop.host}:${laptop.port}', style: muted),
                      selected: _host.text == laptop.host,
                      onTap: () => setState(() {
                        _host.text = laptop.host;
                        _port = laptop.port;
                      }),
                    ),
                  const SizedBox(height: 8),
                  TextField(
                    key: const ValueKey('pair-host'),
                    controller: _host,
                    keyboardType: TextInputType.url,
                    decoration: InputDecoration(labelText: tr(c, 'Laptop ka address (jaise 192.168.1.5)', 'Laptop address (e.g. 192.168.1.5)')),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const ValueKey('pair-code'),
                    controller: _code,
                    keyboardType: TextInputType.number,
                    maxLength: 6,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    style: const TextStyle(fontSize: 22, letterSpacing: 8, color: RishuColors.text),
                    decoration: InputDecoration(labelText: tr(c, 'Laptop par dikh raha code', 'Code shown on the laptop'), counterText: ''),
                    onSubmitted: (_) => _pair(),
                  ),
                  if (_error.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(_error, style: const TextStyle(color: RishuColors.red)),
                  ],
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    key: const ValueKey('pair-button'),
                    onPressed: _busy ? null : _pair,
                    icon: _busy
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.link_rounded),
                    label: Text(tr(c, 'Jodo', 'Connect')),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    tr(c, 'Connection encrypted rehta hai. Phone se boli baat laptop wala Rishu karta hai: LMS, sheets, WhatsApp Desktop sab.',
                        'The connection is encrypted. The laptop\'s Rishu does the work: LMS, sheets, WhatsApp Desktop and more.'),
                    textAlign: TextAlign.center,
                    style: muted,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
