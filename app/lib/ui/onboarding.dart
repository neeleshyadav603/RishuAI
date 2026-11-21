// First run: welcome, about you, Rishu's brain (free Groq key), ready.
import 'package:flutter/material.dart';

import '../core/connection.dart';
import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'orb.dart';
import 'settings.dart' show LanguagePicker, keyProblem;
import 'theme.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  int _step = 0;
  final _name = TextEditingController();
  final _key = TextEditingController();
  String _language = 'hi';
  String _script = 'devanagari';
  String _gender = 'male';
  bool _working = false;
  String _keyMessage = '';
  bool _keyOk = false;

  @override
  void dispose() {
    _name.dispose();
    _key.dispose();
    super.dispose();
  }

  AssistantController get c => widget.controller;

  Future<void> _saveProfile() async {
    setState(() => _working = true);
    try {
      await c.updateSettings({
        'user_name': _name.text.trim(),
        'language': _language,
        'script': _script,
        'voice_gender': _gender,
      });
      setState(() => _step = 2);
    } catch (e) {
      _snack('$e');
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _checkKey() async {
    final key = _key.text.trim();
    if (key.isEmpty) return;
    setState(() {
      _working = true;
      _keyMessage = tr(c, 'Key check kar raha hoon…', 'Checking the key…');
    });
    final code = await c.testKey('groq', key);
    if (code == 'ok' || code == 'quota') {
      try {
        await c.saveKey('groq', key);
        _keyOk = true;
        _keyMessage = tr(c, '✓ Badhiya! Key sahi hai aur safely save ho gayi.', '✓ Great! The key works and is saved securely.');
      } catch (e) {
        _keyMessage = '$e';
      }
    } else {
      _keyOk = false;
      _keyMessage = keyProblem(c, code);
    }
    if (mounted) setState(() => _working = false);
  }

  void _snack(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  void _preview() {
    final name = _name.text.trim();
    c.speak(_language == 'en'
        ? 'Hi${name.isEmpty ? '' : ' $name'}! I am Rishu, your personal assistant.'
        : 'नमस्ते${name.isEmpty ? '' : ' $name'}! मैं रिशु हूँ, आपका पर्सनल असिस्टेंट।');
  }

  @override
  Widget build(BuildContext context) {
    final pages = [_welcome(), _about(), _brain(), _ready()];
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(0, -0.6),
            radius: 1.3,
            colors: [Color(0xFF1B1550), RishuColors.background],
          ),
        ),
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 620),
              child: Column(
                children: [
                  Orb(mood: _working ? OrbMood.thinking : c.mood, level: c.level, size: _step == 0 ? 200 : 120),
                  const SizedBox(height: 20),
                  _Dots(step: _step, count: pages.length),
                  const SizedBox(height: 20),
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 350),
                    transitionBuilder: (child, a) => FadeTransition(
                      opacity: a,
                      child: SlideTransition(
                        position: Tween(begin: const Offset(0.06, 0), end: Offset.zero).animate(a),
                        child: child,
                      ),
                    ),
                    child: KeyedSubtree(key: ValueKey(_step), child: pages[_step]),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _card(List<Widget> children) => Container(
        padding: const EdgeInsets.all(26),
        decoration: glass(radius: 22, glow: true),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
      );

  Widget _title(String text) =>
      Text(text, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: RishuColors.text));

  Widget _body(String text) =>
      Text(text, style: const TextStyle(fontSize: 15, height: 1.5, color: RishuColors.muted));

  Widget _welcome() => _card([
        _title('Namaste! Main Rishu hoon 👋'),
        const SizedBox(height: 10),
        _body('Aapka personal AI assistant. Main Hindi, Hinglish aur English samajhta hoon, '
            'aapke computer par apps aur websites khol sakta hoon, web se dhoondh kar padha sakta hoon, '
            'aur bolkar jawab deta hoon. Har zaroori kaam se pehle aapse poochhunga.'),
        const SizedBox(height: 22),
        Row(
          children: [
            FilledButton.icon(
              onPressed: () => setState(() => _step = 1),
              icon: const Icon(Icons.arrow_forward_rounded),
              label: const Text('Shuru karte hain'),
            ),
          ],
        ),
      ]);

  Widget _about() => _card([
        _title(tr(c, 'Thoda apne baare mein batao', 'Tell me about you')),
        const SizedBox(height: 16),
        TextField(
          controller: _name,
          autofocus: true,
          decoration: InputDecoration(labelText: tr(c, 'Aapka naam', 'Your name'), hintText: 'Neelesh'),
        ),
        const SizedBox(height: 18),
        _body(tr(c, 'Main kis bhasha mein baat karun?', 'Which language should I speak?')),
        const SizedBox(height: 8),
        LanguagePicker(
          language: _language,
          script: _script,
          onChanged: (language, script) => setState(() {
            _language = language;
            _script = script;
          }),
        ),
        const SizedBox(height: 18),
        _body(tr(c, 'Meri awaaz kaisi ho?', 'Pick my voice')),
        const SizedBox(height: 8),
        Row(
          children: [
            SegmentedButton<String>(
              segments: [
                ButtonSegment(value: 'male', label: Text(tr(c, 'Ladka', 'Male')), icon: const Icon(Icons.face_rounded)),
                ButtonSegment(value: 'female', label: Text(tr(c, 'Ladki', 'Female')), icon: const Icon(Icons.face_3_rounded)),
              ],
              selected: {_gender},
              onSelectionChanged: (v) => setState(() => _gender = v.first),
            ),
            const SizedBox(width: 12),
            OutlinedButton.icon(
              onPressed: () async {
                await c.updateSettings({'voice_gender': _gender, 'language': _language, 'script': _script}).catchError((_) {});
                _preview();
              },
              icon: const Icon(Icons.play_arrow_rounded),
              label: Text(tr(c, 'Sunao', 'Preview')),
            ),
          ],
        ),
        const SizedBox(height: 24),
        Row(
          children: [
            TextButton(onPressed: () => setState(() => _step = 0), child: Text(tr(c, 'Peeche', 'Back'))),
            const Spacer(),
            FilledButton.icon(
              onPressed: _working ? null : _saveProfile,
              icon: const Icon(Icons.arrow_forward_rounded),
              label: Text(tr(c, 'Aage', 'Next')),
            ),
          ],
        ),
      ]);

  Widget _brain() => _card([
        _title(tr(c, 'Mera dimaag jodo 🧠', 'Connect my brain 🧠')),
        const SizedBox(height: 10),
        _body(tr(
          c,
          'Mujhe sochne aur sunne ke liye ek free Groq API key chahiye. 1 minute lagega:\n'
              '1. Neeche "Free key banao" dabao (Google se login kar sakte ho)\n'
              '2. "Create API Key" dabao aur key copy karo\n'
              '3. Yahan paste karo aur "Check + Save" dabao',
          'I need a free Groq API key to think and to listen. It takes a minute:\n'
              '1. Press "Get a free key" (you can sign in with Google)\n'
              '2. Press "Create API Key" and copy it\n'
              '3. Paste it here and press "Check + Save"',
        )),
        const SizedBox(height: 14),
        OutlinedButton.icon(
          onPressed: () => openInBrowser('https://console.groq.com/keys'),
          icon: const Icon(Icons.open_in_new_rounded),
          label: Text(tr(c, 'Free key banao (console.groq.com)', 'Get a free key (console.groq.com)')),
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _key,
                obscureText: true,
                decoration: const InputDecoration(hintText: 'gsk_...'),
                onSubmitted: (_) => _checkKey(),
              ),
            ),
            const SizedBox(width: 10),
            FilledButton(
              onPressed: _working ? null : _checkKey,
              child: Text(tr(c, 'Check + Save', 'Check + Save')),
            ),
          ],
        ),
        if (_keyMessage.isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(_keyMessage,
              style: TextStyle(color: _keyOk ? RishuColors.green : RishuColors.amber, fontSize: 14)),
        ],
        const SizedBox(height: 10),
        _body(tr(c, '🔒 Key sirf is computer par, Windows ke secure store mein encrypted rehti hai.',
            '🔒 The key stays on this computer, encrypted in the Windows secure store.')),
        if (c.localModel.downloaded) ...[
          const SizedBox(height: 6),
          _body(tr(c, '💡 Key ke bina bhi Rishu chalegi: laptop par chhota offline dimaag hai (dheema aur simple). Key ke saath tez aur zyada samajhdaar.',
              '💡 Rishu also works without a key: a small offline brain runs on this laptop (slower, simpler). With a key it is faster and smarter.')),
        ],
        const SizedBox(height: 22),
        Row(
          children: [
            TextButton(
              onPressed: () => setState(() => _step = 3),
              child: Text(c.localModel.downloaded
                  ? tr(c, 'Bina key ke chalao (offline dimaag)', 'Continue without a key (offline brain)')
                  : tr(c, 'Abhi nahi (offline mode)', 'Not now (offline mode)')),
            ),
            const Spacer(),
            FilledButton.icon(
              onPressed: _keyOk ? () => setState(() => _step = 3) : null,
              icon: const Icon(Icons.arrow_forward_rounded),
              label: Text(tr(c, 'Aage', 'Next')),
            ),
          ],
        ),
      ]);

  Widget _ready() => _card([
        _title(tr(c, 'Sab taiyaar hai! 🎉', 'All set! 🎉')),
        const SizedBox(height: 12),
        _tip(Icons.mic_rounded, tr(c, 'Mic button dabao (ya Ctrl+Space) aur bolo. Chup hote hi main samajh jaunga.',
            'Press the mic (or Ctrl+Space) and speak. I stop listening when you pause.')),
        _tip(Icons.apps_rounded, tr(c, '"Chrome kholo", "gitm.edu.in kholo", "notepad kholo"',
            '"Open Chrome", "open gitm.edu.in", "open notepad"')),
        _tip(Icons.school_rounded, tr(c, '"Mujhe quantum computing padhao" — phir beech mein sawaal poochho',
            '"Teach me quantum computing" — and ask questions as we go')),
        _tip(Icons.stop_circle_rounded, tr(c, 'Kabhi bhi rokna ho: STOP button ya Esc', 'To stop anytime: the STOP button or Esc')),
        _tip(Icons.shield_rounded, tr(c, 'Zaroori kaam se pehle main hamesha permission maangunga',
            'I always ask before important actions')),
        const SizedBox(height: 22),
        Row(
          children: [
            const Spacer(),
            FilledButton.icon(
              onPressed: () {
                c.finishOnboarding(skipped: !_keyOk);
                final name = _name.text.trim();
                c.speak(_language == 'en'
                    ? 'Welcome${name.isEmpty ? '' : ' $name'}! I am ready.'
                    : 'स्वागत है${name.isEmpty ? '' : ' $name'}! मैं तैयार हूँ।');
              },
              icon: const Icon(Icons.rocket_launch_rounded),
              label: Text(tr(c, 'Rishu shuru karo', 'Start Rishu')),
            ),
          ],
        ),
      ]);

  Widget _tip(IconData icon, String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: RishuColors.violet, size: 20),
            const SizedBox(width: 12),
            Expanded(child: Text(text, style: const TextStyle(color: RishuColors.text, fontSize: 14.5, height: 1.4))),
          ],
        ),
      );
}

class _Dots extends StatelessWidget {
  const _Dots({required this.step, required this.count});
  final int step;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < count; i++)
          AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            margin: const EdgeInsets.symmetric(horizontal: 4),
            width: i == step ? 26 : 8,
            height: 8,
            decoration: BoxDecoration(
              color: i <= step ? RishuColors.violet : RishuColors.border,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
      ],
    );
  }
}
