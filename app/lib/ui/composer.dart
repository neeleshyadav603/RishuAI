// The input row: text box, the big mic button, STOP while Rishu is busy.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'theme.dart';

class Composer extends StatefulWidget {
  const Composer({super.key, required this.controller, required this.textController, required this.focus});
  final AssistantController controller;
  final TextEditingController textController;
  final FocusNode focus;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  void _send() {
    final text = widget.textController.text;
    if (text.trim().isEmpty || widget.controller.busy) return;
    widget.controller.sendText(text);
    widget.textController.clear();
    widget.focus.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Focus(
              onKeyEvent: (node, event) {
                if (event is KeyDownEvent &&
                    event.logicalKey == LogicalKeyboardKey.enter &&
                    !HardwareKeyboard.instance.isShiftPressed) {
                  _send();
                  return KeyEventResult.handled;
                }
                return KeyEventResult.ignored;
              },
              child: TextField(
                controller: widget.textController,
                focusNode: widget.focus,
                minLines: 1,
                maxLines: 6,
                style: const TextStyle(fontSize: 15, color: RishuColors.text),
                decoration: InputDecoration(
                  hintText: c.listening
                      ? tr(c, 'Sun raha hoon… bolo', 'Listening… speak now')
                      : tr(c, 'Rishu se kuch bhi poocho ya kaam bolo…', 'Ask Rishu anything or give a task…'),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                  suffixIcon: IconButton(
                    tooltip: tr(c, 'Bhejo (Enter)', 'Send (Enter)'),
                    onPressed: c.busy ? null : _send,
                    icon: const Icon(Icons.send_rounded),
                    color: RishuColors.violet,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            transitionBuilder: (child, a) => ScaleTransition(scale: a, child: child),
            child: c.canStop && !c.listening
                ? _RoundButton(
                    key: const ValueKey('stop'),
                    tooltip: tr(c, 'Ruko (STOP)', 'Stop'),
                    icon: Icons.stop_rounded,
                    colors: const [Color(0xFFFF5C7A), Color(0xFFB8325A)],
                    onTap: c.stop,
                  )
                : _RoundButton(
                    key: const ValueKey('mic'),
                    tooltip: c.listening
                        ? tr(c, 'Bas, ho gaya (sunna band)', 'Done speaking')
                        : tr(c, 'Bolo (Ctrl+Space)', 'Speak (Ctrl+Space)'),
                    icon: c.listening ? Icons.graphic_eq_rounded : Icons.mic_rounded,
                    colors: c.listening
                        ? const [Color(0xFF3DD6F5), Color(0xFF1E88B8)]
                        : const [Color(0xFF8D7EFF), Color(0xFF5B4BEA)],
                    pulse: c.listening,
                    level: c.level,
                    onTap: c.toggleListening,
                  ),
          ),
        ],
      ),
    );
  }
}

class _RoundButton extends StatefulWidget {
  const _RoundButton({
    super.key,
    required this.tooltip,
    required this.icon,
    required this.colors,
    required this.onTap,
    this.pulse = false,
    this.level = 0,
  });
  final String tooltip;
  final IconData icon;
  final List<Color> colors;
  final VoidCallback onTap;
  final bool pulse;
  final double level;

  @override
  State<_RoundButton> createState() => _RoundButtonState();
}

class _RoundButtonState extends State<_RoundButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final glow = widget.pulse ? 10 + widget.level * 30 : (_hover ? 18.0 : 8.0);
    return Tooltip(
      message: widget.tooltip,
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() => _hover = false),
        child: GestureDetector(
          onTap: widget.onTap,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(colors: widget.colors, begin: Alignment.topLeft, end: Alignment.bottomRight),
              boxShadow: [BoxShadow(color: widget.colors.first.withValues(alpha: 0.5), blurRadius: glow, spreadRadius: 1)],
            ),
            child: Icon(widget.icon, color: Colors.white, size: 26),
          ),
        ),
      ),
    );
  }
}
