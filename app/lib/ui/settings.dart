// Settings: name, language, voice, permissions, AI brain (API keys), about.
import 'package:flutter/material.dart';

import '../core/connection.dart';
import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'lock.dart' show SecuritySettings;
import 'offline.dart' show OfflineModelSettings;
import 'phone_link.dart' show PhoneLinkSettings;
import 'teach.dart' show TaughtSkills;
import 'theme.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _name = TextEditingController(text: widget.controller.userName);
  late final TextEditingController _address =
      TextEditingController(text: '${widget.controller.settings['address_as'] ?? ''}');
  late final TextEditingController _about =
      TextEditingController(text: '${widget.controller.settings['about_me'] ?? ''}');

  @override
  void initState() {
    super.initState();
    widget.controller.refreshSettings().catchError((_) {});
  }

  @override
  void dispose() {
    _name.dispose();
    _address.dispose();
    _about.dispose();
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
          icon: Icons.favorite_rounded,
          title: tr(c, 'Rishu ka andaaz', 'Rishu\'s style'),
          children: [
            Row(
              children: [
                Expanded(
                  child: _PersonaCard(
                    key: const ValueKey('persona-professional'),
                    selected: s['persona'] != 'personal',
                    icon: Icons.work_rounded,
                    title: tr(c, 'Professional', 'Professional'),
                    text: tr(c, 'Shaant, seedha aur saaf. College, class ya client ke saamne ke liye.',
                        'Calm, direct and clear. For college, class or clients.'),
                    sample: tr(c, '"Ho gaya. Attendance save kar di hai."', '"Done. The attendance is saved."'),
                    onTap: () => _save({'persona': 'professional'}),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _PersonaCard(
                    key: const ValueKey('persona-personal'),
                    selected: s['persona'] == 'personal',
                    icon: Icons.favorite_rounded,
                    title: tr(c, 'Personal', 'Personal'),
                    text: tr(c, 'Apnapan, pyaar aur thodi masti. Sirf aapke liye wala andaaz.',
                        'Warm, caring and a little playful. Your own companion style.'),
                    sample: tr(c, '"Ho gaya! Aaj bahut kaam kiya aapne, thoda aaram bhi kar lijiye."',
                        '"Done! You worked a lot today, take a little rest too."'),
                    onTap: () async {
                      // The personal style speaks in a woman's voice by default (changeable below).
                      await _save({'persona': 'personal', if (s['persona'] != 'personal') 'voice_gender': 'female'});
                      c.speak(c.english
                          ? 'Hi${c.userName.isEmpty ? '' : ' ${c.userName}'}! I am here for you, always.'
                          : 'हाय${c.userName.isEmpty ? '' : ' ${c.userName}'}! मैं हूँ ना, आपके साथ।');
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    key: const ValueKey('address-as'),
                    controller: _address,
                    maxLength: 40,
                    decoration: InputDecoration(
                      labelText: tr(c, 'Rishu aapko kya bulaye?', 'What should Rishu call you?'),
                      hintText: tr(c, 'jaise: Sir, Neelesh ji', 'e.g. Sir, Neelesh'),
                      counterText: '',
                    ),
                    onSubmitted: (v) => _save({'address_as': v}),
                  ),
                ),
                const SizedBox(width: 12),
                FilledButton(onPressed: () => _save({'address_as': _address.text}), child: Text(tr(c, 'Save', 'Save'))),
              ],
            ),
            const SizedBox(height: 12),
            TextField(
              key: const ValueKey('about-me'),
              controller: _about,
              maxLength: 600,
              minLines: 2,
              maxLines: 5,
              decoration: InputDecoration(
                labelText: tr(c, 'Apne baare mein aur baat karne ka tareeka', 'About you and how Rishu should talk'),
                hintText: tr(c, 'jaise: Main GITM mein Assistant Professor hoon. Chhote jawab do. Subah 9 baje class hoti hai.',
                    'e.g. I teach at GITM. Keep answers short. My classes start at 9.'),
                alignLabelWithHint: true,
              ),
            ),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.tonal(
                key: const ValueKey('save-about-me'),
                onPressed: () => _save({'about_me': _about.text}),
                child: Text(tr(c, 'Yaad rakho', 'Save')),
              ),
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
            SwitchListTile(
              key: const ValueKey('follow-up'),
              contentPadding: EdgeInsets.zero,
              value: s['follow_up'] == true,
              onChanged: c.speakReplies ? (v) => _save({'follow_up': v}) : null,
              title: Text(tr(c, 'Baat-cheet mode: jawab ke baad mic khud khule', 'Conversation mode: listen again after each spoken reply')),
              subtitle: Text(tr(c, '"Bas" ya "Thank you" bolo to band. Shor wali jagah par off rakho.',
                  'Say "bas" or "thank you" to end. Keep it off in noisy rooms.')),
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
          icon: Icons.phone_android_rounded,
          title: tr(c, 'Phone se jodo', 'Phone link'),
          children: [PhoneLinkSettings(controller: c)],
        ),
        _Section(
          icon: Icons.offline_bolt_rounded,
          title: tr(c, 'Offline dimaag', 'Offline brain'),
          children: [OfflineModelSettings(controller: c)],
        ),
        _Section(
          icon: Icons.school_rounded,
          title: tr(c, 'Seekhe hue kaam', 'Taught tasks'),
          children: [TaughtSkills(controller: c)],
        ),
        _Section(
          icon: Icons.lock_rounded,
          title: tr(c, 'Suraksha (lock)', 'Security (lock)'),
          children: [SecuritySettings(controller: c)],
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
      // List tiles paint on the nearest Material: give them one above the glass.
      child: Material(
        type: MaterialType.transparency,
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


class _PersonaCard extends StatelessWidget {
  const _PersonaCard({
    super.key,
    required this.selected,
    required this.icon,
    required this.title,
    required this.text,
    required this.sample,
    required this.onTap,
  });
  final bool selected;
  final IconData icon;
  final String title;
  final String text;
  final String sample;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final accent = selected ? RishuColors.violet : RishuColors.border;
    return Material(
      color: selected ? RishuColors.violet.withValues(alpha: 0.12) : RishuColors.panelHigh,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: accent, width: selected ? 2 : 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, color: selected ? RishuColors.violet : RishuColors.muted),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(title,
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: RishuColors.text)),
                  ),
                  if (selected) const Icon(Icons.check_circle_rounded, color: RishuColors.violet, size: 20),
                ],
              ),
              const SizedBox(height: 8),
              Text(text, style: const TextStyle(color: RishuColors.muted, fontSize: 13)),
              const SizedBox(height: 8),
              Text(sample, style: const TextStyle(color: RishuColors.text, fontStyle: FontStyle.italic, fontSize: 13)),
            ],
          ),
        ),
      ),
    );
  }
}
