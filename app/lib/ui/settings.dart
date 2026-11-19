// Settings: name, language, voice, permissions, AI brain (API keys), about.
import 'package:flutter/material.dart';

import '../core/connection.dart';
import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'theme.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _name = TextEditingController(text: widget.controller.userName);

  @override
  void initState() {
    super.initState();
    widget.controller.refreshSettings().catchError((_) {});
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save(Map<String, dynamic> patch) async {
    try {
      await widget.controller.updateSettings(patch);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final s = c.settings;
    return ListView(
      padding: const EdgeInsets.fromLTRB(32, 28, 32, 40),
      children: [
        Text(tr(c, 'Settings', 'Settings'),
            style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: RishuColors.text)),
        const SizedBox(height: 20),
        _Section(
          icon: Icons.person_rounded,
          title: tr(c, 'Aap', 'You'),
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _name,
                    decoration: InputDecoration(labelText: tr(c, 'Aapka naam', 'Your name')),
                    onSubmitted: (v) => _save({'user_name': v}),
                  ),
                ),
                const SizedBox(width: 12),
                FilledButton(onPressed: () => _save({'user_name': _name.text}), child: Text(tr(c, 'Save', 'Save'))),
              ],
            ),
            const SizedBox(height: 16),
            Text(tr(c, 'Rishu kis bhasha mein baat kare?', 'Which language should Rishu use?'),
                style: const TextStyle(color: RishuColors.muted)),
            const SizedBox(height: 8),
            LanguagePicker(
              language: '${s['language'] ?? 'auto'}',
              script: '${s['script'] ?? 'roman'}',
              onChanged: (language, script) => _save({'language': language, 'script': script}),
            ),
          ],
        ),
        _Section(
          icon: Icons.record_voice_over_rounded,
          title: tr(c, 'Awaaz', 'Voice'),
          children: [
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: c.speakReplies,
              onChanged: (v) => _save({'speak_replies': v}),
              title: Text(tr(c, 'Jawab bolkar sunao', 'Speak replies aloud')),
              subtitle: Text(c.voice.output
                  ? tr(c, 'Natural Hindi/English awaaz (internet), warna Windows ki awaaz', 'Natural voices online, Windows voices offline')
                  : tr(c, 'Is device par awaaz available nahi hai', 'No voice output on this device')),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Text(tr(c, 'Rishu ki awaaz:', 'Rishu\'s voice:'), style: const TextStyle(color: RishuColors.muted)),
                const SizedBox(width: 12),
                SegmentedButton<String>(
                  segments: [
                    ButtonSegment(value: 'male', label: Text(tr(c, 'Ladka', 'Male')), icon: const Icon(Icons.face_rounded)),
                    ButtonSegment(value: 'female', label: Text(tr(c, 'Ladki', 'Female')), icon: const Icon(Icons.face_3_rounded)),
                  ],
                  selected: {'${s['voice_gender'] ?? 'male'}'},
                  onSelectionChanged: (v) async {
                    await _save({'voice_gender': v.first});
                    c.speak(c.english ? 'Hello! This is my voice now.' : 'नमस्ते! अब मेरी आवाज़ ऐसी है।');
                  },
                ),
                const SizedBox(width: 12),
                OutlinedButton.icon(
                  onPressed: () => c.speak(c.english
                      ? 'Hi${c.userName.isEmpty ? '' : ' ${c.userName}'}, I am Rishu, your personal assistant.'
                      : 'नमस्ते${c.userName.isEmpty ? '' : ' ${c.userName}'}, मैं रिशु हूँ, आपका पर्सनल असिस्टेंट।'),
                  icon: const Icon(Icons.play_arrow_rounded),
                  label: Text(tr(c, 'Sunao', 'Preview')),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _InfoRow(
              ok: c.voice.input,
              text: c.voice.input
                  ? tr(c, 'Mic taiyaar hai. Shortcut: Ctrl+Space (app ke andar)', 'Mic ready. Shortcut: Ctrl+Space (inside the app)')
                  : tr(c, 'Mic abhi band hai: ${c.voice.inputReason}', 'Mic is off: ${c.voice.inputReason}'),
            ),
          ],
        ),
        _Section(
          icon: Icons.shield_rounded,
          title: tr(c, 'Permission', 'Permissions'),
          children: [
            Text(
              tr(c, 'Rishu koi bhi kaam karne se pehle kitna poochhe?', 'How often should Rishu ask before acting?'),
              style: const TextStyle(color: RishuColors.muted),
            ),
            const SizedBox(height: 8),
            for (final (value, hi, en) in const [
              ('ask_always', 'Har kaam se pehle poochho', 'Ask before every action'),
              ('smart', 'Smart: sirf zaroori kaamon par poochho (recommended)', 'Smart: ask only for important actions (recommended)'),
              ('trusted_skills', 'Bharose wale kaam bina pooche karo', 'Run trusted skills without asking'),
            ])
              ListTile(
                contentPadding: EdgeInsets.zero,
                onTap: () => _save({'autonomy': value}),
                leading: Icon(
                  '${s['autonomy'] ?? 'smart'}' == value
                      ? Icons.radio_button_checked_rounded
                      : Icons.radio_button_unchecked_rounded,
                  color: '${s['autonomy'] ?? 'smart'}' == value ? RishuColors.violet : RishuColors.muted,
                ),
                title: Text(tr(c, hi, en)),
              ),
            const SizedBox(height: 4),
            Text(
              tr(c, 'Message bhejna, file delete karna ya paise wale kaam: Rishu hamesha poochhega.',
                  'Sending messages, deleting files or anything with money: Rishu always asks.'),
              style: const TextStyle(color: RishuColors.muted, fontSize: 12.5),
            ),
          ],
        ),
        _Section(
          icon: Icons.psychology_rounded,
          title: tr(c, 'AI brain (API key)', 'AI brain (API key)'),
          children: [
            for (final p in c.providers.where((p) => !p.local)) ProviderTile(controller: c, provider: p),
          ],
        ),
        _Section(
          icon: Icons.info_rounded,
          title: tr(c, 'Rishu ke baare mein', 'About Rishu'),
          children: [
            Text('Rishu ${c.version.isEmpty ? '' : 'v${c.version}'}', style: const TextStyle(color: RishuColors.text)),
            const SizedBox(height: 4),
            Text(
              tr(c, 'Aapka data (notes, settings, keys) sirf is computer par rehta hai. Keys Windows ke secure store mein encrypted hain.',
                  'Your data (notes, settings, keys) stays on this computer. Keys are encrypted in the Windows secure store.'),
              style: const TextStyle(color: RishuColors.muted, fontSize: 13),
            ),
          ],
        ),
      ],
    );
  }
}

class LanguagePicker extends StatelessWidget {
  const LanguagePicker({super.key, required this.language, required this.script, required this.onChanged});
  final String language;
  final String script;
  final void Function(String language, String script) onChanged;

  @override
  Widget build(BuildContext context) {
    final current = language == 'en'
        ? 'en'
        : (script == 'devanagari' ? 'hi' : 'hinglish');
    return SegmentedButton<String>(
      segments: const [
        ButtonSegment(value: 'hi', label: Text('हिंदी')),
        ButtonSegment(value: 'hinglish', label: Text('Hinglish')),
        ButtonSegment(value: 'en', label: Text('English')),
      ],
      selected: {current},
      onSelectionChanged: (v) {
        switch (v.first) {
          case 'hi':
            onChanged('hi', 'devanagari');
          case 'hinglish':
            onChanged('hinglish', 'roman');
          default:
            onChanged('en', 'roman');
        }
      },
    );
  }
}

class ProviderTile extends StatefulWidget {
  const ProviderTile({super.key, required this.controller, required this.provider});
  final AssistantController controller;
  final Provider provider;

  @override
  State<ProviderTile> createState() => _ProviderTileState();
}

class _ProviderTileState extends State<ProviderTile> {
  final _key = TextEditingController();
  bool _editing = false;
  bool _working = false;
  String _message = '';

  @override
  void dispose() {
    _key.dispose();
    super.dispose();
  }

  Future<void> _testAndSave() async {
    final c = widget.controller;
    final key = _key.text.trim();
    if (key.isEmpty) return;
    setState(() {
      _working = true;
      _message = tr(c, 'Key check kar raha hoon…', 'Checking the key…');
    });
    final code = await c.testKey(widget.provider.name, key);
    if (code == 'ok' || code == 'quota') {
      try {
        await c.saveKey(widget.provider.name, key);
        _message = tr(c, '✓ Key sahi hai aur save ho gayi', '✓ Key works and is saved');
        _editing = false;
        _key.clear();
      } catch (e) {
        _message = '$e';
      }
    } else {
      _message = keyProblem(c, code);
    }
    if (mounted) setState(() => _working = false);
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final p = widget.provider;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: RishuColors.panelHigh,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: p.configured ? RishuColors.green.withValues(alpha: 0.35) : RishuColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(p.configured ? Icons.check_circle_rounded : Icons.circle_outlined,
                  color: p.configured ? RishuColors.green : RishuColors.muted, size: 18),
              const SizedBox(width: 8),
              Text(p.label, style: const TextStyle(fontWeight: FontWeight.w700, color: RishuColors.text)),
              const SizedBox(width: 8),
              Text(
                p.configured
                    ? (p.keySource == 'env' ? tr(c, '(system se)', '(from system)') : tr(c, '(saved)', '(saved)'))
                    : tr(c, '(key nahi hai)', '(no key)'),
                style: const TextStyle(color: RishuColors.muted, fontSize: 12.5),
              ),
              const Spacer(),
              if (p.keyUrl.isNotEmpty)
                TextButton(onPressed: () => openInBrowser(p.keyUrl), child: Text(tr(c, 'Free key lo', 'Get a free key'))),
              if (!_editing)
                TextButton(
                  onPressed: () => setState(() => _editing = true),
                  child: Text(p.configured ? tr(c, 'Badlo', 'Change') : tr(c, 'Key daalo', 'Add key')),
                ),
              if (p.configured && p.keySource == 'saved' && !_editing)
                IconButton(
                  tooltip: tr(c, 'Key hatao', 'Remove key'),
                  onPressed: () => c.deleteKey(p.name).catchError((_) {}),
                  icon: const Icon(Icons.delete_outline_rounded, color: RishuColors.muted),
                ),
            ],
          ),
          if (_editing) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _key,
                    obscureText: true,
                    decoration: InputDecoration(hintText: tr(c, '${p.label} API key paste karo', 'Paste your ${p.label} API key')),
                    onSubmitted: (_) => _testAndSave(),
                  ),
                ),
                const SizedBox(width: 10),
                FilledButton(
                  onPressed: _working ? null : _testAndSave,
                  child: Text(tr(c, 'Test + Save', 'Test + Save')),
                ),
              ],
            ),
          ],
          if (_message.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_message, style: const TextStyle(color: RishuColors.muted, fontSize: 13)),
            ),
        ],
      ),
    );
  }
}

String keyProblem(AssistantController c, String code) => switch (code) {
      'auth' => tr(c, '✕ Yeh key galat hai ya band ho chuki hai.', '✕ This key was rejected.'),
      'invalid_key' => tr(c, '✕ Key sahi format mein nahi hai.', '✕ The key is not in the right format.'),
      'unreachable' => tr(c, '✕ Internet nahi mil raha. Connection check karo.', '✕ No internet connection.'),
      'no_key' => tr(c, '✕ Pehle key paste karo.', '✕ Paste a key first.'),
      _ => tr(c, '✕ Key check nahi ho paayi. Dobara try karo.', '✕ Could not check the key. Try again.'),
    };

class _Section extends StatelessWidget {
  const _Section({required this.icon, required this.title, required this.children});
  final IconData icon;
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      padding: const EdgeInsets.all(20),
      constraints: const BoxConstraints(maxWidth: 820),
      decoration: glass(radius: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: RishuColors.violet),
              const SizedBox(width: 10),
              Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: RishuColors.text)),
            ],
          ),
          const SizedBox(height: 14),
          ...children,
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.ok, required this.text});
  final bool ok;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(ok ? Icons.check_circle_rounded : Icons.info_outline_rounded,
            size: 16, color: ok ? RishuColors.green : RishuColors.amber),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: const TextStyle(color: RishuColors.muted, fontSize: 13))),
      ],
    );
  }
}
