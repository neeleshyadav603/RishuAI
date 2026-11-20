// Teach mode UI: the recording banner and the list of taught skills.
import 'package:flutter/material.dart';

import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'theme.dart';

class TeachBanner extends StatefulWidget {
  const TeachBanner({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<TeachBanner> createState() => _TeachBannerState();
}

class _TeachBannerState extends State<TeachBanner> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final teach = c.teach;
    final recent = teach.steps.length > 3 ? teach.steps.sublist(teach.steps.length - 3) : teach.steps;
    return Container(
      key: const ValueKey('teach-banner'),
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      padding: const EdgeInsets.all(14),
      decoration: glass(radius: 16, tint: RishuColors.pink, glow: true),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              FadeTransition(
                opacity: Tween(begin: 0.35, end: 1.0).animate(_pulse),
                child: const Icon(Icons.fiber_manual_record_rounded, color: RishuColors.red, size: 16),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  tr(c, 'Seekh rahi hoon: ${teach.task}', 'Learning: ${teach.task}'),
                  style: const TextStyle(color: RishuColors.text, fontWeight: FontWeight.w700),
                ),
              ),
              Text(
                tr(c, '${teach.steps.length} step', '${teach.steps.length} steps'),
                style: const TextStyle(color: RishuColors.muted, fontSize: 12.5),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            tr(c, 'Rishu ki browser window mein kaam ek baar karke dikhaiye. Ho jaaye to "Bas, ho gaya" dabaiye ya boliye.',
                'Show the task once in Rishu\'s browser window. Then press or say "Done".'),
            style: const TextStyle(color: RishuColors.muted, fontSize: 13),
          ),
          for (final step in recent)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(
                children: [
                  const Icon(Icons.check_circle_rounded, size: 14, color: RishuColors.green),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(step,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: RishuColors.text, fontSize: 13)),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 10),
          Row(
            children: [
              FilledButton.icon(
                key: const ValueKey('teach-done'),
                onPressed: c.teachDone,
                icon: const Icon(Icons.done_all_rounded),
                label: Text(tr(c, 'Bas, ho gaya', 'Done')),
              ),
              const SizedBox(width: 10),
              TextButton(onPressed: c.teachCancel, child: Text(tr(c, 'Cancel', 'Cancel'))),
            ],
          ),
        ],
      ),
    );
  }
}

/// Settings: what the user has taught Rishu, with a delete button each.
class TaughtSkills extends StatelessWidget {
  const TaughtSkills({super.key, required this.controller});
  final AssistantController controller;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final skills = c.teach.skills;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          tr(c, 'Jo kaam Rishu nahi jaanti, use ek baar karke dikhaiye: bolo "Rishu, main tumhe ek kaam sikhata hoon". Agli baar wo khud kar degi.',
              'Show Rishu a task once: say "Rishu, let me teach you something". Next time it does it itself.'),
          style: const TextStyle(color: RishuColors.muted, fontSize: 13),
        ),
        const SizedBox(height: 10),
        if (skills.isEmpty)
          Text(tr(c, 'Abhi koi kaam nahi sikhaya.', 'Nothing taught yet.'),
              style: const TextStyle(color: RishuColors.muted))
        else
          for (final skill in skills)
            ListTile(
              key: ValueKey('skill-${skill.name}'),
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.school_rounded, color: RishuColors.cyan),
              title: Text(skill.name, style: const TextStyle(color: RishuColors.text)),
              subtitle: Text(
                '${skill.description} · ${tr(c, '${skill.steps} step', '${skill.steps} steps')}',
                style: const TextStyle(color: RishuColors.muted, fontSize: 12.5),
              ),
              trailing: IconButton(
                tooltip: tr(c, 'Bhool jao', 'Forget'),
                icon: const Icon(Icons.delete_outline_rounded),
                onPressed: () => c.forgetSkill(skill.name),
              ),
            ),
      ],
    );
  }
}
