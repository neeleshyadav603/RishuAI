// Activity log: everything Rishu did, with its risk level and how it was approved.
import 'package:flutter/material.dart';

import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'theme.dart';

class ActivityScreen extends StatefulWidget {
  const ActivityScreen({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<ActivityScreen> createState() => _ActivityScreenState();
}

class _ActivityScreenState extends State<ActivityScreen> {
  late Future<List<Map<String, dynamic>>> _entries = widget.controller.activity();

  String _when(num? ts) {
    if (ts == null) return '';
    final t = DateTime.fromMillisecondsSinceEpoch((ts * 1000).round());
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(t.day)}/${two(t.month)} ${two(t.hour)}:${two(t.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 28, 32, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(tr(c, 'Rishu ne kya kiya', 'What Rishu did'),
                  style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: RishuColors.text)),
              const Spacer(),
              IconButton(
                tooltip: tr(c, 'Refresh', 'Refresh'),
                onPressed: () => setState(() => _entries = c.activity()),
                icon: const Icon(Icons.refresh_rounded, color: RishuColors.muted),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            tr(c, 'Har kaam ka record: kab, kya, kitna risky, aur kisne allow kiya.',
                'A record of every action: when, what, how risky, and how it was approved.'),
            style: const TextStyle(color: RishuColors.muted),
          ),
          const SizedBox(height: 18),
          Expanded(
            child: FutureBuilder<List<Map<String, dynamic>>>(
              future: _entries,
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                final entries = snap.data ?? const [];
                if (entries.isEmpty) {
                  return Center(
                    child: Text(tr(c, 'Abhi tak koi kaam nahi hua.', 'Nothing yet.'),
                        style: const TextStyle(color: RishuColors.muted)),
                  );
                }
                return ListView.separated(
                  itemCount: entries.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (context, i) {
                    final e = entries[i];
                    final ok = e['ok'] == true;
                    final approval = '${e['approval'] ?? ''}';
                    final color = ok
                        ? RishuColors.green
                        : (approval == 'denied' || approval == 'forbidden' ? RishuColors.amber : RishuColors.red);
                    return Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      decoration: glass(radius: 12),
                      child: Row(
                        children: [
                          Icon(ok ? Icons.check_circle_rounded : Icons.cancel_rounded, color: color, size: 20),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('${e['tool'] ?? ''}',
                                    style: const TextStyle(color: RishuColors.text, fontWeight: FontWeight.w600)),
                                Text(
                                  '${e['args'] ?? ''}',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(color: RishuColors.muted, fontSize: 12.5),
                                ),
                              ],
                            ),
                          ),
                          _Tag('${e['risk'] ?? ''}'),
                          const SizedBox(width: 8),
                          _Tag(approval),
                          const SizedBox(width: 12),
                          Text(_when(e['ts'] as num?), style: const TextStyle(color: RishuColors.muted, fontSize: 12)),
                        ],
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    if (text.isEmpty) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: RishuColors.violet.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(text, style: const TextStyle(color: RishuColors.text, fontSize: 11.5)),
    );
  }
}
