// Settings: connect a phone (laptop side), or the paired laptop (phone side).
import 'package:flutter/material.dart';

import '../state/assistant.dart';
import 'chat.dart' show tr;
import 'theme.dart';

class PhoneLinkSettings extends StatefulWidget {
  const PhoneLinkSettings({super.key, required this.controller});
  final AssistantController controller;

  @override
  State<PhoneLinkSettings> createState() => _PhoneLinkSettingsState();
}

class _PhoneLinkSettingsState extends State<PhoneLinkSettings> {
  AssistantController get c => widget.controller;

  @override
  void initState() {
    super.initState();
    if (!c.onPhone) c.refreshPhoneLink().catchError((Object _) {});
  }

  Future<void> _run(Future<void> Function() action) async {
    try {
      await action();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    const muted = TextStyle(color: RishuColors.muted, fontSize: 13);
    if (c.onPhone) {
      if (c.onPhoneBrain) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.phone_android_rounded, color: RishuColors.cyan),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                      tr(c, 'Rishu abhi phone par khud chal rahi hai (online AI: Groq etc.).',
                          'Rishu is running on the phone itself (online AI: Groq etc.).'),
                      style: const TextStyle(color: RishuColors.text)),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              tr(c, 'LMS, Excel/Word, WhatsApp Desktop aur teach mode laptop par hote hain. Laptop jodne se phone se bhi ho jayenge.',
                  'LMS, Excel/Word, WhatsApp Desktop and teach mode run on the laptop. Pair it to use them from the phone.'),
              style: muted,
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              key: const ValueKey('pair-laptop-button'),
              onPressed: () => _run(c.unpairLaptop),
              icon: const Icon(Icons.laptop_windows_rounded),
              label: Text(tr(c, 'Laptop se jodo', 'Pair with the laptop')),
            ),
          ],
        );
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.laptop_windows_rounded, color: RishuColors.cyan),
              const SizedBox(width: 10),
              Expanded(
                child: Text(tr(c, 'Yeh phone laptop wale Rishu se juda hai.', 'This phone is connected to Rishu on the laptop.'),
                    style: const TextStyle(color: RishuColors.text)),
              ),
              TextButton(onPressed: () => _run(c.unpairLaptop), child: Text(tr(c, 'Alag karo', 'Disconnect'))),
            ],
          ),
          Text(
            tr(c, 'Laptop band ho ya door ho to phone apne online dimaag (Groq key) se chalega.',
                'When the laptop is off or away, the phone uses its own online brain (Groq key).'),
            style: muted,
          ),
          TextButton.icon(
            onPressed: () => _run(() => c.setPhoneMode('phone')),
            icon: const Icon(Icons.phone_android_rounded),
            label: Text(tr(c, 'Abhi phone par hi chalao', 'Use the phone brain now')),
          ),
        ],
      );
    }
    final link = c.phoneLink;
    final codeValid = link.code.isNotEmpty && link.codeUntil != null && link.codeUntil!.isAfter(DateTime.now());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          tr(c, 'Phone par Rishu app kholo aur yahan dikha code daalo. Phone aur laptop ek hi Wi-Fi par hon. Phone se boli baat yeh laptop karega.',
              'Open Rishu on the phone and enter the code shown here. Both on the same Wi-Fi; this laptop does the work.'),
          style: muted,
        ),
        const SizedBox(height: 12),
        if (codeValid) ...[
          Container(
            key: const ValueKey('phone-code'),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            decoration: glass(radius: 14, tint: RishuColors.cyan, glow: true),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(link.code, style: const TextStyle(fontSize: 34, letterSpacing: 10, fontWeight: FontWeight.w800, color: RishuColors.text)),
                const SizedBox(height: 4),
                Text(
                  '${tr(c, 'Laptop ka address', 'Laptop address')}: ${link.addresses.isEmpty ? '—' : link.addresses.join(' / ')}  ·  port ${link.port}',
                  style: muted,
                ),
                Text(tr(c, 'Code 10 minute tak chalega.', 'The code works for 10 minutes.'), style: muted),
              ],
            ),
          ),
          const SizedBox(height: 10),
        ],
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            FilledButton.icon(
              key: const ValueKey('phone-start'),
              onPressed: () => _run(c.startPhoneLink),
              icon: const Icon(Icons.phone_android_rounded),
              label: Text(codeValid ? tr(c, 'Naya code', 'New code') : tr(c, 'Phone jodo', 'Connect a phone')),
            ),
            if (link.running)
              OutlinedButton(onPressed: () => _run(c.stopPhoneLink), child: Text(tr(c, 'Phone link band karo', 'Turn off phone link'))),
          ],
        ),
        if (link.running) ...[
          const SizedBox(height: 6),
          Text(
            tr(c, 'Windows Firewall poochhe to "Private networks" par Allow karo.', 'If Windows Firewall asks, allow it on private networks.'),
            style: muted,
          ),
        ],
        const SizedBox(height: 10),
        for (final device in link.devices)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.smartphone_rounded, color: RishuColors.green),
            title: Text(device['name'] ?? '', style: const TextStyle(color: RishuColors.text)),
            trailing: IconButton(
              tooltip: tr(c, 'Hatao', 'Remove'),
              icon: const Icon(Icons.link_off_rounded),
              onPressed: () => _run(() => c.removePhone(device['id'] ?? '')),
            ),
          ),
      ],
    );
  }
}
