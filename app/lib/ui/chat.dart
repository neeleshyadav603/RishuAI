// The conversation: bubbles, live steps, approval cards, sources and notices.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/connection.dart';
import '../state/assistant.dart';
import 'markdown.dart';
import 'theme.dart';

String tr(AssistantController c, String hinglish, String english) => c.english ? english : hinglish;

class ChatList extends StatefulWidget {
  const ChatList({super.key, required this.controller, required this.onSuggestion});
  final AssistantController controller;
  final ValueChanged<String> onSuggestion;

  @override
  State<ChatList> createState() => _ChatListState();
}

class _ChatListState extends State<ChatList> {
  final _scroll = ScrollController();
  int _lastCount = 0;
  int _lastLength = 0;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _followBottom() {
    final c = widget.controller;
    final length = c.items.isEmpty ? 0 : (c.items.last is AssistantItem ? (c.items.last as AssistantItem).text.length : 0);
    if (c.items.length == _lastCount && length == _lastLength) return;
    _lastCount = c.items.length;
    _lastLength = length;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOutCubic,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    if (c.items.isEmpty) return EmptyChat(controller: c, onSuggestion: widget.onSuggestion);
    _followBottom();
    final showTyping = c.busy && (c.items.last is! AssistantItem || !(c.items.last as AssistantItem).streaming);
    return SelectionArea(
      child: ListView.builder(
        controller: _scroll,
        padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
        itemCount: c.items.length + (showTyping ? 1 : 0),
        itemBuilder: (context, i) {
          if (i == c.items.length) return const _Appear(key: ValueKey('typing'), child: TypingDots());
          final item = c.items[i];
          return _Appear(key: ValueKey(item.id), child: _item(item));
        },
      ),
    );
  }

  Widget _item(ChatItem item) {
    final c = widget.controller;
    if (item is UserItem) return UserBubble(item: item);
    if (item is AssistantItem) return AssistantBubble(item: item, controller: c);
    if (item is ToolItem) return ToolStep(item: item);
    if (item is ApprovalItem) return ApprovalCard(item: item, controller: c);
    if (item is SourcesItem) return SourcesCard(item: item, controller: c);
    if (item is NoticeItem) return NoticeLine(item: item);
    return const SizedBox.shrink();
  }
}

class _Appear extends StatelessWidget {
  const _Appear({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOutCubic,
      builder: (context, t, child) => Opacity(
        opacity: t,
        child: Transform.translate(offset: Offset(0, 14 * (1 - t)), child: child),
      ),
      child: child,
    );
  }
}

class EmptyChat extends StatelessWidget {
  const EmptyChat({super.key, required this.controller, required this.onSuggestion});
  final AssistantController controller;
  final ValueChanged<String> onSuggestion;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final name = c.userName.isEmpty ? '' : ', ${c.userName}';
    final suggestions = c.english
        ? const [
            ('🌐', 'Open Chrome'),
            ('📰', 'Search today\'s AI news'),
            ('🎓', 'Teach me quantum computing'),
            ('⛅', 'Weather in Gurugram'),
            ('⏰', 'Remind me in 1 minute to drink water'),
            ('🎵', 'Play Kesariya on YouTube'),
            ('🔎', 'Open gitm.edu.in'),
            ('🧠', 'Remember: my favourite subject is DAA'),
          ]
        : const [
            ('🌐', 'Chrome kholo'),
            ('📰', 'Aaj ki AI news search karo'),
            ('🎓', 'Mujhe quantum computing padhao'),
            ('⛅', 'Gurugram ka mausam batao'),
            ('⏰', '1 minute baad paani peene ka reminder lagao'),
            ('🎵', 'YouTube pe Kesariya chalao'),
            ('🔎', 'gitm.edu.in kholo'),
            ('🧠', 'Yaad rakho: mera favourite subject DAA hai'),
          ];
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 680),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                tr(c, 'Namaste$name! Main kya madad karun?', 'Hi$name! How can I help?'),
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: RishuColors.text),
              ),
              const SizedBox(height: 8),
              Text(
                c.voice.input
                    ? tr(c, 'Mic dabao aur bolo, ya neeche type karo.', 'Press the mic and speak, or type below.')
                    : tr(c, 'Neeche type karo, ya kisi suggestion par click karo.', 'Type below, or pick a suggestion.'),
                textAlign: TextAlign.center,
                style: const TextStyle(color: RishuColors.muted, fontSize: 15),
              ),
              const SizedBox(height: 28),
              Wrap(
                alignment: WrapAlignment.center,
                spacing: 10,
                runSpacing: 10,
                children: [
                  for (final (icon, text) in suggestions) _SuggestionChip(icon: icon, text: text, onTap: () => onSuggestion(text)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SuggestionChip extends StatefulWidget {
  const _SuggestionChip({required this.icon, required this.text, required this.onTap});
  final String icon;
  final String text;
  final VoidCallback onTap;

  @override
  State<_SuggestionChip> createState() => _SuggestionChipState();
}

class _SuggestionChipState extends State<_SuggestionChip> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          transform: Matrix4.translationValues(0, _hover ? -2 : 0, 0),
          decoration: glass(radius: 14, glow: _hover, tint: _hover ? RishuColors.cyan : RishuColors.violet),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(widget.icon, style: const TextStyle(fontSize: 16)),
              const SizedBox(width: 8),
              Text(widget.text, style: const TextStyle(color: RishuColors.text, fontSize: 14)),
            ],
          ),
        ),
      ),
    );
  }
}

class UserBubble extends StatelessWidget {
  const UserBubble({super.key, required this.item});
  final UserItem item;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.only(top: 10, bottom: 4, left: 80),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [Color(0xFF5B4BEA), Color(0xFF7C6CFF)]),
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(18),
            topRight: Radius.circular(18),
            bottomLeft: Radius.circular(18),
            bottomRight: Radius.circular(6),
          ),
          boxShadow: [BoxShadow(color: RishuColors.violet.withValues(alpha: 0.25), blurRadius: 16)],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (item.voice) ...[
              const Padding(
                padding: EdgeInsets.only(top: 2, right: 8),
                child: Icon(Icons.mic_rounded, size: 16, color: Colors.white70),
              ),
            ],
            Flexible(child: Text(item.text, style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.45))),
          ],
        ),
      ),
    );
  }
}

class AssistantBubble extends StatelessWidget {
  const AssistantBubble({super.key, required this.item, required this.controller});
  final AssistantItem item;
  final AssistantController controller;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(top: 10, bottom: 4, right: 60),
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
        decoration: glass(radius: 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: LinearGradient(colors: [RishuColors.cyan, RishuColors.violet]),
                  ),
                ),
                const SizedBox(width: 8),
                const Text('Rishu', style: TextStyle(color: RishuColors.muted, fontSize: 12.5, fontWeight: FontWeight.w600)),
              ],
            ),
            const SizedBox(height: 6),
            MarkdownText(item.text + (item.streaming ? ' ▍' : '')),
            if (!item.streaming)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _MiniButton(
                    icon: Icons.volume_up_rounded,
                    tooltip: tr(controller, 'Sunao', 'Read aloud'),
                    onTap: () => controller.speak(item.text),
                  ),
                  _MiniButton(
                    icon: Icons.copy_rounded,
                    tooltip: tr(controller, 'Copy karo', 'Copy'),
                    onTap: () => Clipboard.setData(ClipboardData(text: item.text)),
                  ),
                  if (item.provider.isNotEmpty && item.provider != 'mock')
                    Padding(
                      padding: const EdgeInsets.only(left: 6),
                      child: Text(item.provider, style: const TextStyle(color: RishuColors.muted, fontSize: 11)),
                    ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _MiniButton extends StatelessWidget {
  const _MiniButton({required this.icon, required this.tooltip, required this.onTap});
  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Icon(icon, size: 16, color: RishuColors.muted),
        ),
      ),
    );
  }
}

class ToolStep extends StatelessWidget {
  const ToolStep({super.key, required this.item});
  final ToolItem item;

  @override
  Widget build(BuildContext context) {
    final (icon, color) = switch (item.status) {
      ToolStatus.running => (Icons.bolt_rounded, RishuColors.amber),
      ToolStatus.done => (Icons.check_circle_rounded, RishuColors.green),
      ToolStatus.failed => (Icons.error_rounded, RishuColors.red),
      ToolStatus.denied => (Icons.block_rounded, RishuColors.muted),
    };
    final text = item.status == ToolStatus.failed && item.summary.isNotEmpty ? item.summary : item.message;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (item.status == ToolStatus.running)
              SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2, color: color),
              )
            else
              Icon(icon, size: 16, color: color),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                text,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: RishuColors.text, fontSize: 13),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ApprovalCard extends StatefulWidget {
  const ApprovalCard({super.key, required this.item, required this.controller});
  final ApprovalItem item;
  final AssistantController controller;

  @override
  State<ApprovalCard> createState() => _ApprovalCardState();
}

class _ApprovalCardState extends State<ApprovalCard> {
  final _pin = TextEditingController();

  ApprovalItem get item => widget.item;

  @override
  void dispose() {
    _pin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final stepUp = item.decision == 'step_up';
    final pending = item.status == ApprovalStatus.pending;
    final accent = item.risk == 'R3' ? RishuColors.red : RishuColors.amber;
    final status = switch (item.status) {
      ApprovalStatus.pending => '',
      ApprovalStatus.approved => tr(c, '✓ Aapne allow kiya', '✓ You allowed this'),
      ApprovalStatus.denied => tr(c, '✕ Mana kar diya', '✕ Denied'),
      ApprovalStatus.expired => tr(c, '⌛ Time khatam, nahi kiya', '⌛ Timed out, not done'),
      ApprovalStatus.blocked => tr(
          c,
          '🔒 Is bade kaam ke liye Rishu PIN + Windows Hello chahiye (Settings > Suraksha)',
          '🔒 Needs Rishu\'s PIN + Windows Hello (Settings > Security)',
        ),
    };
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 560),
        margin: const EdgeInsets.symmetric(vertical: 8),
        padding: const EdgeInsets.all(16),
        decoration: glass(radius: 16, tint: accent, glow: pending),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.shield_rounded, color: accent, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    tr(c, 'Rishu aapki permission maang raha hai', 'Rishu needs your permission'),
                    style: const TextStyle(fontWeight: FontWeight.w700, color: RishuColors.text),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(item.risk, style: TextStyle(color: accent, fontSize: 12, fontWeight: FontWeight.w700)),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(item.preview, style: const TextStyle(color: RishuColors.text, fontSize: 15, height: 1.4)),
            const SizedBox(height: 12),
            if (pending) ...[
              _Countdown(seconds: item.timeoutSeconds, color: accent, onDone: () => c.expire(item)),
              const SizedBox(height: 12),
              if (stepUp) ...[
                Text(
                  tr(c, 'Bada kaam hai: Rishu PIN daalo, phir PC par Windows Hello se pehchaan dikhao.',
                      'High risk: enter Rishu\'s PIN, then confirm with Windows Hello on the PC.'),
                  style: const TextStyle(color: RishuColors.muted, fontSize: 13),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: 220,
                  child: TextField(
                    key: ValueKey('step-up-pin-${item.callId}'),
                    controller: _pin,
                    obscureText: true,
                    maxLength: 12,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'PIN', counterText: ''),
                  ),
                ),
                const SizedBox(height: 10),
              ],
              Row(
                children: [
                  FilledButton.icon(
                    style: FilledButton.styleFrom(backgroundColor: RishuColors.green, foregroundColor: Colors.black),
                    onPressed: () => stepUp ? c.answer(item, true, pin: _pin.text.trim()) : c.answer(item, true),
                    icon: Icon(stepUp ? Icons.fingerprint_rounded : Icons.check_rounded),
                    label: Text(stepUp ? tr(c, 'PIN + Windows Hello se karo', 'Approve with PIN + Hello') : tr(c, 'Haan, karo', 'Yes, do it')),
                  ),
                  const SizedBox(width: 10),
                  OutlinedButton.icon(
                    onPressed: () => c.answer(item, false),
                    icon: const Icon(Icons.close_rounded),
                    label: Text(tr(c, 'Nahi', 'No')),
                  ),
                ],
              ),
            ] else
              Text(status, style: const TextStyle(color: RishuColors.muted, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

class _Countdown extends StatelessWidget {
  const _Countdown({required this.seconds, required this.color, required this.onDone});
  final double seconds;
  final Color color;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 1, end: 0),
      duration: Duration(milliseconds: (seconds * 1000).round()),
      onEnd: onDone,
      builder: (context, v, _) => ClipRRect(
        borderRadius: BorderRadius.circular(4),
        child: LinearProgressIndicator(
          value: v,
          minHeight: 4,
          color: color,
          backgroundColor: color.withValues(alpha: 0.12),
        ),
      ),
    );
  }
}

class SourcesCard extends StatelessWidget {
  const SourcesCard({super.key, required this.item, required this.controller});
  final SourcesItem item;
  final AssistantController controller;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 620),
        margin: const EdgeInsets.symmetric(vertical: 6),
        padding: const EdgeInsets.all(12),
        decoration: glass(radius: 14, tint: RishuColors.cyan),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.travel_explore_rounded, size: 18, color: RishuColors.cyan),
                const SizedBox(width: 8),
                Text(
                  tr(controller, 'Sources (${item.sources.length})', 'Sources (${item.sources.length})'),
                  style: const TextStyle(color: RishuColors.text, fontWeight: FontWeight.w700, fontSize: 13.5),
                ),
              ],
            ),
            const SizedBox(height: 6),
            for (final (i, s) in item.sources.indexed)
              InkWell(
                borderRadius: BorderRadius.circular(8),
                onTap: () => openInBrowser(s.url),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 4),
                  child: Row(
                    children: [
                      Container(
                        width: 20,
                        height: 20,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: RishuColors.cyan.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text('${i + 1}', style: const TextStyle(fontSize: 11, color: RishuColors.cyan)),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(s.title, maxLines: 1, overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: RishuColors.text, fontSize: 13.5)),
                            Text(Uri.tryParse(s.url)?.host ?? s.url, maxLines: 1, overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: RishuColors.muted, fontSize: 12)),
                          ],
                        ),
                      ),
                      const Icon(Icons.open_in_new_rounded, size: 15, color: RishuColors.muted),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class NoticeLine extends StatelessWidget {
  const NoticeLine({super.key, required this.item});
  final NoticeItem item;

  @override
  Widget build(BuildContext context) {
    final color = item.error ? RishuColors.red : (item.reminder ? RishuColors.amber : RishuColors.muted);
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 620),
        margin: const EdgeInsets.symmetric(vertical: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.25)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(item.error ? Icons.info_rounded : (item.reminder ? Icons.alarm_rounded : Icons.lightbulb_outline_rounded),
                size: 16, color: color),
            const SizedBox(width: 8),
            Flexible(child: Text(item.text, style: TextStyle(color: color, fontSize: 13, height: 1.4))),
          ],
        ),
      ),
    );
  }
}

class TypingDots extends StatefulWidget {
  const TypingDots({super.key});

  @override
  State<TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<TypingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(top: 10),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        decoration: glass(radius: 18),
        child: AnimatedBuilder(
          animation: _c,
          builder: (context, _) => Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (var i = 0; i < 3; i++)
                Container(
                  margin: const EdgeInsets.symmetric(horizontal: 3),
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: RishuColors.violet.withValues(
                      alpha: 0.35 + 0.65 * (0.5 + 0.5 * _wave(_c.value - i * 0.15)),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  double _wave(double v) {
    final x = (v % 1.0) * 2 - 1;
    return 1 - x.abs() * 2;
  }
}
