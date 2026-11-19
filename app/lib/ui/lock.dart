// Lock screen: PIN, Windows Hello or the spoken password.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'orb.dart';
import 'theme.dart';

class LockScreen extends StatefulWidget {
  const LockScreen({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  final _pin = TextEditingController();
  final _focus = FocusNode();

  AssistantController get c => widget.controller;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _focus.requestFocus());
  }

  @override
  void dispose() {
    _pin.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _submit() {
    final pin = _pin.text.trim();
    if (pin.length < 4) return;
    c.unlockWithPin(pin);
    _pin.clear();
    _focus.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final lock = c.lock;
    final listening = c.mood == OrbMood.listening;
    final checking = c.mood == OrbMood.thinking;
    return Container(
      decoration: const BoxDecoration(
        gradient: RadialGradient(
          center: Alignment(0, -0.35),
          radius: 1.2,
          colors: [Color(0xFF1A1440), RishuColors.background],
        ),
      ),
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 380),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Orb(mood: listening ? OrbMood.listening : OrbMood.locked, level: c.level, size: 150),
                const SizedBox(height: 18),
                const Icon(Icons.lock_rounded, color: RishuColors.violet, size: 26),
                const SizedBox(height: 8),
                Text(
                  tr(c, 'Rishu locked hai', 'Rishu is locked'),
                  style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: RishuColors.text),
                ),
                const SizedBox(height: 6),
                Text(
                  listening
                      ? tr(c, 'Sun raha hoon… apna password bolo', 'Listening… say your password')
                      : checking
                          ? tr(c, 'Check kar raha hoon…', 'Checking…')
                          : tr(c, 'Unlock karne ke liye PIN daalo', 'Enter your PIN to unlock'),
                  style: const TextStyle(color: RishuColors.muted),
                ),
                const SizedBox(height: 22),
                TextField(
                  key: const ValueKey('lock-pin'),
                  controller: _pin,
                  focusNode: _focus,
                  obscureText: true,
                  textAlign: TextAlign.center,
                  maxLength: 12,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  style: const TextStyle(fontSize: 22, letterSpacing: 10, color: RishuColors.text),
                  decoration: InputDecoration(
                    counterText: '',
                    hintText: '••••',
                    suffixIcon: IconButton(
                      tooltip: tr(c, 'Unlock', 'Unlock'),
                      onPressed: _submit,
                      icon: const Icon(Icons.arrow_forward_rounded, color: RishuColors.violet),
                    ),
                  ),
                  onSubmitted: (_) => _submit(),
                ),
                AnimatedSize(
                  duration: const Duration(milliseconds: 200),
                  child: c.lockError.isEmpty
                      ? const SizedBox(height: 14)
                      : Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: Text(c.lockError,
                              key: const ValueKey('lock-error'),
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: RishuColors.red)),
                        ),
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  alignment: WrapAlignment.center,
                  children: [
                    if (lock.hello)
                      OutlinedButton.icon(
                        onPressed: checking ? null : c.unlockWithHello,
                        icon: const Icon(Icons.fingerprint_rounded),
                        label: const Text('Windows Hello'),
                      ),
                    if (lock.phraseSet)
                      OutlinedButton.icon(
                        onPressed: listening || checking ? null : c.unlockWithVoice,
                        icon: const Icon(Icons.mic_rounded),
                        label: Text(tr(c, 'Bolkar unlock', 'Unlock by voice')),
                      ),
                  ],
                ),
                const SizedBox(height: 22),
                Text(
                  tr(c, 'Lock rehte hue Rishu na kuch dikhata hai na kuch karta hai.',
                      'While locked, Rishu shows nothing and does nothing.'),
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: RishuColors.muted, fontSize: 12.5),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Settings section: PIN, spoken password, Windows Hello, lock now.
class SecuritySettings extends StatefulWidget {
  const SecuritySettings({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<SecuritySettings> createState() => _SecuritySettingsState();
}

class _SecuritySettingsState extends State<SecuritySettings> {
  AssistantController get c => widget.controller;

  void _snack(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _setPin({required bool change}) async {
    final result = await showDialog<(String, String?)>(
      context: context,
      builder: (_) => _PinDialog(controller: c, askCurrent: change),
    );
    if (result == null) return;
    try {
      await c.setPin(result.$1, current: result.$2);
      _snack(tr(c, 'PIN save ho gaya. Ab Rishu lock ho sakta hai.', 'PIN saved. Rishu can lock now.'));
    } catch (e) {
      _snack('$e');
    }
  }

  Future<void> _removePin() async {
    final result = await showDialog<(String, String?)>(
      context: context,
      builder: (_) => _PinDialog(controller: c, askCurrent: true, removing: true),
    );
    if (result == null) return;
    try {
      await c.removePin(result.$2 ?? '');
      _snack(tr(c, 'PIN hata diya. Ab lock band hai.', 'PIN removed. Locking is off.'));
    } catch (e) {
      _snack('$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final lock = c.lock;
    const muted = TextStyle(color: RishuColors.muted, fontSize: 13);
    if (!lock.pinSet) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            tr(c, 'PIN set karo taaki aapke alawa koi Rishu use na kar sake. Phir Windows Hello aur bolkar password bhi chalega.',
                'Set a PIN so only you can use Rishu. Windows Hello and a spoken password work after that.'),
            style: muted,
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            key: const ValueKey('set-pin'),
            onPressed: () => _setPin(change: false),
            icon: const Icon(Icons.pin_rounded),
            label: Text(tr(c, 'PIN set karo', 'Set a PIN')),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            FilledButton.icon(
              onPressed: c.lockNow,
              icon: const Icon(Icons.lock_rounded),
              label: Text(tr(c, 'Abhi lock karo', 'Lock now')),
            ),
            OutlinedButton(onPressed: () => _setPin(change: true), child: Text(tr(c, 'PIN badlo', 'Change PIN'))),
            TextButton(onPressed: _removePin, child: Text(tr(c, 'PIN hatao', 'Remove PIN'))),
          ],
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            const Icon(Icons.record_voice_over_rounded, color: RishuColors.cyan, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                lock.phraseSet
                    ? tr(c, 'Bolkar password set hai', 'Spoken password is set')
                    : tr(c, 'Bolkar password: lock screen par bolkar unlock karo', 'Spoken password: unlock by saying a phrase'),
                style: const TextStyle(color: RishuColors.text),
              ),
            ),
            if (lock.phraseSet)
              TextButton(
                onPressed: () => c.removePhrase().catchError((Object e) => _snack('$e')),
                child: Text(tr(c, 'Hatao', 'Remove')),
              ),
            OutlinedButton.icon(
              onPressed: c.voice.input && c.mood != OrbMood.listening ? c.enrollPhrase : null,
              icon: Icon(c.mood == OrbMood.listening ? Icons.graphic_eq_rounded : Icons.mic_rounded),
              label: Text(c.mood == OrbMood.listening
                  ? tr(c, 'Bolo…', 'Speak…')
                  : lock.phraseSet
                      ? tr(c, 'Naya record karo', 'Record again')
                      : tr(c, 'Record karo', 'Record')),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Icon(lock.hello ? Icons.fingerprint_rounded : Icons.do_not_touch_rounded,
                color: lock.hello ? RishuColors.green : RishuColors.muted, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                lock.hello
                    ? tr(c, 'Windows Hello (fingerprint / face / Windows PIN) se bhi unlock hoga',
                        'Windows Hello (fingerprint / face / Windows PIN) can unlock too')
                    : tr(c, 'Windows Hello is PC par set nahi hai', 'Windows Hello is not set up on this PC'),
                style: const TextStyle(color: RishuColors.text),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          tr(
              c,
              '${lock.idleMinutes.round()} minute kuch na karne par Rishu khud lock ho jaata hai. Turant lock: bolo "Rishu lock". '
                  'Awaaz ki nakal ho sakti hai, isliye bolkar password sirf unlock karta hai, koi bada kaam approve nahi karta.',
              'Rishu locks itself after ${lock.idleMinutes.round()} minutes without use. Lock at once: say "Rishu lock". '
                  'Voices can be imitated, so the spoken password only unlocks; it never approves risky actions.'),
          style: muted,
        ),
      ],
    );
  }
}

class _PinDialog extends StatefulWidget {
  const _PinDialog({required this.controller, required this.askCurrent, this.removing = false});
  final AssistantController controller;
  final bool askCurrent;
  final bool removing;

  @override
  State<_PinDialog> createState() => _PinDialogState();
}

class _PinDialogState extends State<_PinDialog> {
  final _current = TextEditingController();
  final _pin = TextEditingController();
  final _again = TextEditingController();
  String _error = '';

  AssistantController get c => widget.controller;

  @override
  void dispose() {
    _current.dispose();
    _pin.dispose();
    _again.dispose();
    super.dispose();
  }

  Widget _field(TextEditingController controller, String label, {bool autofocus = false}) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: TextField(
          controller: controller,
          autofocus: autofocus,
          obscureText: true,
          maxLength: 12,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          decoration: InputDecoration(labelText: label, counterText: ''),
          onSubmitted: (_) => _done(),
        ),
      );

  void _done() {
    final current = widget.askCurrent ? _current.text : null;
    if (widget.removing) {
      Navigator.pop(context, ('', current));
      return;
    }
    final pin = _pin.text;
    if (pin.length < 4) {
      setState(() => _error = tr(c, 'PIN kam se kam 4 ank ka ho', 'The PIN needs at least 4 digits'));
      return;
    }
    if (pin != _again.text) {
      setState(() => _error = tr(c, 'Dono PIN match nahi hue', 'The two PINs do not match'));
      return;
    }
    Navigator.pop(context, (pin, current));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.removing
          ? tr(c, 'PIN hatao', 'Remove PIN')
          : widget.askCurrent
              ? tr(c, 'PIN badlo', 'Change PIN')
              : tr(c, 'Naya PIN', 'New PIN')),
      content: SizedBox(
        width: 320,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (widget.askCurrent) _field(_current, tr(c, 'Abhi wala PIN', 'Current PIN'), autofocus: true),
            if (!widget.removing) ...[
              _field(_pin, tr(c, 'Naya PIN (4-12 ank)', 'New PIN (4-12 digits)'), autofocus: !widget.askCurrent),
              _field(_again, tr(c, 'Naya PIN dobara', 'New PIN again')),
            ],
            if (_error.isNotEmpty) Text(_error, style: const TextStyle(color: RishuColors.red)),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(tr(c, 'Cancel', 'Cancel'))),
        FilledButton(onPressed: _done, child: Text(tr(c, 'Theek hai', 'OK'))),
      ],
    );
  }
}
