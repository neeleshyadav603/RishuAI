// Main window: sidebar, the orb panel, and the conversation.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../state/assistant.dart';
import 'activity.dart';
import 'chat.dart';
import 'composer.dart';
import 'orb.dart';
import 'settings.dart';
import 'theme.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _tab = 0;
  final _text = TextEditingController();
  final _focus = FocusNode();

  @override
  void dispose() {
    _text.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _suggest(String text) {
    widget.controller.sendText(text);
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.space, control: true): c.toggleListening,
        const SingleActivator(LogicalKeyboardKey.escape): c.stop,
        const SingleActivator(LogicalKeyboardKey.keyN, control: true): c.newConversation,
      },
      child: Focus(
        autofocus: true,
        child: Scaffold(
          body: Stack(
            children: [
              const _Backdrop(),
              Row(
                children: [
                  _Sidebar(
                    controller: c,
                    tab: _tab,
                    onTab: (i) => setState(() => _tab = i),
                  ),
                  Expanded(
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 250),
                      child: switch (_tab) {
                        1 => ActivityScreen(key: const ValueKey('activity'), controller: c),
                        2 => SettingsScreen(key: const ValueKey('settings'), controller: c),
                        _ => _ChatPane(
                            key: const ValueKey('chat'),
                            controller: c,
                            text: _text,
                            focus: _focus,
                            onSuggestion: _suggest,
                          ),
                      },
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Backdrop extends StatelessWidget {
  const _Backdrop();

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: Alignment(-0.6, -0.8),
          radius: 1.4,
          colors: [Color(0xFF16123A), RishuColors.background],
        ),
      ),
      child: SizedBox.expand(),
    );
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({required this.controller, required this.tab, required this.onTab});
  final AssistantController controller;
  final int tab;
  final ValueChanged<int> onTab;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    return Container(
      width: 84,
      decoration: BoxDecoration(
        color: RishuColors.panel.withValues(alpha: 0.6),
        border: const Border(right: BorderSide(color: RishuColors.border)),
      ),
      child: Column(
        children: [
          const SizedBox(height: 18),
          Orb(mood: c.mood, level: c.level, size: 46),
          const SizedBox(height: 6),
          const Text('Rishu', style: TextStyle(fontWeight: FontWeight.w700, color: RishuColors.text)),
          const SizedBox(height: 22),
          _NavButton(icon: Icons.chat_bubble_rounded, label: tr(c, 'Baat', 'Chat'), selected: tab == 0, onTap: () => onTab(0)),
          _NavButton(icon: Icons.history_rounded, label: tr(c, 'Kaam', 'Activity'), selected: tab == 1, onTap: () => onTab(1)),
          _NavButton(icon: Icons.tune_rounded, label: tr(c, 'Settings', 'Settings'), selected: tab == 2, onTap: () => onTab(2)),
          const Spacer(),
          if (c.lock.pinSet)
            Tooltip(
              message: tr(c, 'Rishu lock karo (ya bolo "Rishu lock")', 'Lock Rishu (or say "Rishu lock")'),
              child: IconButton(
                key: const ValueKey('sidebar-lock'),
                onPressed: c.lockNow,
                icon: const Icon(Icons.lock_outline_rounded, color: RishuColors.muted),
              ),
            ),
          Tooltip(
            message: tr(c, 'Nayi baat-cheet (Ctrl+N)', 'New conversation (Ctrl+N)'),
            child: IconButton(
              onPressed: c.busy
                  ? null
                  : () {
                      c.newConversation();
                      onTab(0);
                    },
              icon: const Icon(Icons.add_comment_rounded, color: RishuColors.muted),
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _NavButton extends StatelessWidget {
  const _NavButton({required this.icon, required this.label, required this.selected, required this.onTap});
  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: 66,
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: selected ? RishuColors.violet.withValues(alpha: 0.18) : Colors.transparent,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Column(
            children: [
              Icon(icon, color: selected ? RishuColors.violet : RishuColors.muted, size: 22),
              const SizedBox(height: 4),
              Text(label,
                  style: TextStyle(fontSize: 11.5, color: selected ? RishuColors.text : RishuColors.muted)),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChatPane extends StatelessWidget {
  const _ChatPane({
    super.key,
    required this.controller,
    required this.text,
    required this.focus,
    required this.onSuggestion,
  });
  final AssistantController controller;
  final TextEditingController text;
  final FocusNode focus;
  final ValueChanged<String> onSuggestion;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    return LayoutBuilder(builder: (context, box) {
      final wide = box.maxWidth > 1080;
      final chat = Column(
        children: [
          _TopBar(controller: c),
          if (c.disconnected) _Disconnected(controller: c),
          Expanded(child: ChatList(controller: c, onSuggestion: onSuggestion)),
          Composer(controller: c, textController: text, focus: focus),
        ],
      );
      if (!wide) return chat;
      return Row(
        children: [
          SizedBox(width: 340, child: _OrbPanel(controller: c)),
          Expanded(child: chat),
        ],
      );
    });
  }
}

class _OrbPanel extends StatelessWidget {
  const _OrbPanel({required this.controller});
  final AssistantController controller;

  String _caption(AssistantController c) => switch (c.mood) {
        OrbMood.listening => tr(c, 'Sun raha hoon…', 'Listening…'),
        OrbMood.thinking => tr(c, 'Soch raha hoon…', 'Thinking…'),
        OrbMood.acting => tr(c, 'Kaam kar raha hoon…', 'Working on it…'),
        OrbMood.speaking => tr(c, 'Bol raha hoon…', 'Speaking…'),
        OrbMood.offline => tr(c, 'Offline', 'Offline'),
        OrbMood.connecting => tr(c, 'Jud raha hoon…', 'Connecting…'),
        OrbMood.locked => tr(c, 'Locked', 'Locked'),
        OrbMood.idle => c.voice.input
            ? tr(c, 'Mic dabao ya Ctrl+Space', 'Press the mic or Ctrl+Space')
            : tr(c, 'Main taiyaar hoon', 'Ready when you are'),
      };

  @override
  Widget build(BuildContext context) {
    final c = controller;
    return Container(
      decoration: const BoxDecoration(border: Border(right: BorderSide(color: RishuColors.border))),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          GestureDetector(
            onTap: c.canStop && !c.listening ? c.stop : c.toggleListening,
            child: MouseRegion(
              cursor: SystemMouseCursors.click,
              child: Orb(mood: c.mood, level: c.level, size: 250),
            ),
          ),
          const SizedBox(height: 18),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 250),
            child: Text(
              _caption(c),
              key: ValueKey(c.mood),
              style: const TextStyle(color: RishuColors.text, fontSize: 17, fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            child: Text(
              tr(c, 'Orb par click karke bhi bol sakte ho', 'Click the orb to talk'),
              textAlign: TextAlign.center,
              style: const TextStyle(color: RishuColors.muted, fontSize: 12.5),
            ),
          ),
          const SizedBox(height: 26),
          _StatusChips(controller: c),
        ],
      ),
    );
  }
}

class _StatusChips extends StatelessWidget {
  const _StatusChips({required this.controller});
  final AssistantController controller;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    Widget chip(IconData icon, String label, bool ok) => Container(
          margin: const EdgeInsets.symmetric(vertical: 3),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            color: (ok ? RishuColors.green : RishuColors.muted).withValues(alpha: 0.1),
            border: Border.all(color: (ok ? RishuColors.green : RishuColors.muted).withValues(alpha: 0.3)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 14, color: ok ? RishuColors.green : RishuColors.muted),
              const SizedBox(width: 6),
              Text(label, style: const TextStyle(fontSize: 12, color: RishuColors.text)),
            ],
          ),
        );
    return Column(
      children: [
        chip(Icons.psychology_rounded, c.hasBrain ? tr(c, 'AI brain: online', 'AI brain: online') : tr(c, 'AI brain: offline mode', 'AI brain: offline mode'), c.hasBrain),
        chip(Icons.mic_rounded, c.voice.input ? tr(c, 'Mic: ready', 'Mic: ready') : tr(c, 'Mic: band', 'Mic: off'), c.voice.input),
        chip(Icons.volume_up_rounded, c.speakReplies && c.voice.output ? tr(c, 'Awaaz: on', 'Voice: on') : tr(c, 'Awaaz: off', 'Voice: off'), c.speakReplies && c.voice.output),
      ],
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.controller});
  final AssistantController controller;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    return Container(
      height: 60,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: RishuColors.border))),
      child: Row(
        children: [
          Text(
            c.userName.isEmpty ? 'Rishu' : tr(c, 'Rishu · ${c.userName} ke liye', 'Rishu · for ${c.userName}'),
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: RishuColors.text),
          ),
          const SizedBox(width: 10),
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: c.disconnected ? RishuColors.red : (c.hasBrain ? RishuColors.green : RishuColors.amber),
            ),
          ),
          const Spacer(),
          Tooltip(
            message: c.speakReplies ? tr(c, 'Jawab bolkar sunana band karo', 'Mute spoken replies') : tr(c, 'Jawab bolkar sunao', 'Speak replies'),
            child: IconButton(
              onPressed: () => c.updateSettings({'speak_replies': !c.speakReplies}).catchError((_) {}),
              icon: Icon(c.speakReplies ? Icons.volume_up_rounded : Icons.volume_off_rounded,
                  color: c.speakReplies ? RishuColors.violet : RishuColors.muted),
            ),
          ),
          Tooltip(
            message: tr(c, 'Nayi baat-cheet', 'New conversation'),
            child: IconButton(
              onPressed: c.busy ? null : c.newConversation,
              icon: const Icon(Icons.refresh_rounded, color: RishuColors.muted),
            ),
          ),
        ],
      ),
    );
  }
}

class _Disconnected extends StatelessWidget {
  const _Disconnected({required this.controller});
  final AssistantController controller;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    return Container(
      width: double.infinity,
      color: RishuColors.red.withValues(alpha: 0.12),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      child: Row(
        children: [
          const Icon(Icons.link_off_rounded, color: RishuColors.red, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              tr(c, 'Rishu ke core se connection toot gaya.', 'Lost the connection to Rishu\'s core.'),
              style: const TextStyle(color: RishuColors.text),
            ),
          ),
          TextButton(onPressed: c.restart, child: Text(tr(c, 'Dobara jodo', 'Reconnect'))),
        ],
      ),
    );
  }
}
