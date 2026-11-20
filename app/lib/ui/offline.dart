// Settings: Rishu's offline model (works without internet, key or daily limit).
import 'package:flutter/material.dart';

import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'theme.dart';

class OfflineModelSettings extends StatelessWidget {
  const OfflineModelSettings({super.key, required this.controller});
  final AssistantController controller;

  Future<void> _run(BuildContext context, Future<void> Function() action) async {
    try {
      await action();
    } catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final m = c.localModel;
    const muted = TextStyle(color: RishuColors.muted, fontSize: 13);
    if (!m.engine) {
      return Text(
        tr(c, 'Is build mein offline engine nahi hai. Ollama install karke bhi offline chala sakte ho.',
            'This build has no offline engine. Ollama also works for offline use.'),
        style: muted,
      );
    }
    final status = m.downloading
        ? tr(c, 'Download ho raha hai… ${(m.fraction * 100).toStringAsFixed(0)}%',
            'Downloading… ${(m.fraction * 100).toStringAsFixed(0)}%')
        : m.downloaded
            ? (m.running
                ? tr(c, 'Taiyaar aur chal raha hai', 'Ready and running')
                : tr(c, 'Taiyaar: internet ya key na ho to Rishu isse chalegi', 'Ready: used when there is no internet or key'))
            : tr(c, 'Abhi download nahi hua', 'Not downloaded yet');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          tr(c, 'Bina internet, bina key, bina limit: laptop par chalne wala chhota dimaag. Online wale se dheema aur simple hai, isliye ye backup hai.',
              'No internet, no key, no limit: a small brain on this laptop. Slower and simpler than online models, so it is the backup.'),
          style: muted,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final entry in m.choices.entries)
              ChoiceChip(
                key: ValueKey('local-${entry.key}'),
                label: Text(entry.value),
                selected: m.choice == entry.key,
                onSelected: m.downloading ? null : (_) => _run(context, () => c.chooseLocalModel(entry.key)),
              ),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Icon(
              m.downloaded ? Icons.offline_bolt_rounded : Icons.cloud_download_rounded,
              color: m.downloaded ? RishuColors.green : RishuColors.muted,
              size: 20,
            ),
            const SizedBox(width: 8),
            Expanded(child: Text(status, style: const TextStyle(color: RishuColors.text))),
          ],
        ),
        if (m.downloading) ...[
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(value: m.fraction, minHeight: 6, color: RishuColors.cyan),
          ),
        ],
        if (m.error.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(m.error, style: const TextStyle(color: RishuColors.red, fontSize: 13)),
        ],
        const SizedBox(height: 10),
        Row(
          children: [
            if (!m.downloaded)
              FilledButton.icon(
                key: const ValueKey('local-download'),
                onPressed: m.downloading ? null : () => _run(context, c.downloadLocalModel),
                icon: const Icon(Icons.download_rounded),
                label: Text(tr(c, 'Download (${m.sizeMb} MB)', 'Download (${m.sizeMb} MB)')),
              )
            else
              TextButton.icon(
                onPressed: () => _run(context, c.deleteLocalModel),
                icon: const Icon(Icons.delete_outline_rounded),
                label: Text(tr(c, 'Hatao (jagah khaali karo)', 'Delete (free the space)')),
              ),
          ],
        ),
      ],
    );
  }
}
