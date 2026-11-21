// Rishu: a voice-first personal AI assistant.
// The app starts the bundled core (Python) and talks to it over a local WebSocket.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'state/assistant.dart';
import 'ui/home.dart';
import 'ui/lock.dart';
import 'ui/onboarding.dart';
import 'ui/pair.dart';
import 'ui/orb.dart';
import 'ui/theme.dart';

const String appVersion = String.fromEnvironment('RISHU_VERSION', defaultValue: 'dev');

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final controller = AssistantController()..boot();
  final smokeFile = Platform.environment['RISHU_SMOKE_FILE'];
  if (smokeFile != null && smokeFile.isNotEmpty) runSmokeTest(controller, File(smokeFile));
  runApp(RishuApp(controller: controller));
}

/// Build check on CI: start the bundled core, run one turn, write the result, exit.
void runSmokeTest(AssistantController controller, File out) {
  var sent = false;
  void finish(String result, int code) {
    out.writeAsStringSync(result);
    exit(code);
  }

  Timer(const Duration(minutes: 3), () => finish('timeout phase=${controller.phase.name} ${controller.bootError}', 1));
  controller.addListener(() {
    if (controller.phase == Phase.failed) finish('failed ${controller.bootError}', 1);
    if (controller.phase == Phase.booting) return;
    if (!sent) {
      sent = true;
      controller.sendText('time kya hua hai');
      return;
    }
    for (final item in controller.items) {
      if (item is AssistantItem && !item.streaming && item.text.isNotEmpty) {
        finish('ok phase=${controller.phase.name} reply=${item.text}', 0);
      }
    }
  });
}

class RishuApp extends StatelessWidget {
  const RishuApp({super.key, required this.controller});
  final AssistantController controller;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Rishu',
      debugShowCheckedModeBanner: false,
      theme: rishuTheme(),
      home: ListenableBuilder(
        listenable: controller,
        builder: (context, _) => AnimatedSwitcher(
          duration: const Duration(milliseconds: 450),
          child: switch (controller.phase) {
            Phase.booting => BootScreen(key: const ValueKey('boot'), controller: controller),
            Phase.failed => BootScreen(key: const ValueKey('failed'), controller: controller),
            Phase.onboarding => OnboardingScreen(key: const ValueKey('onboarding'), controller: controller),
            Phase.ready when controller.locked => LockScreen(key: const ValueKey('lock'), controller: controller),
            Phase.ready => HomeScreen(key: const ValueKey('home'), controller: controller),
            Phase.pairing => PairScreen(key: const ValueKey('pair'), controller: controller),
          },
        ),
      ),
    );
  }
}

class BootScreen extends StatelessWidget {
  const BootScreen({super.key, required this.controller});
  final AssistantController controller;

  @override
  Widget build(BuildContext context) {
    final failed = controller.phase == Phase.failed;
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(0, -0.3),
            radius: 1.2,
            colors: [Color(0xFF1B1550), RishuColors.background],
          ),
        ),
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Orb(mood: failed ? OrbMood.offline : OrbMood.connecting, size: 220),
                const SizedBox(height: 28),
                Text(
                  failed ? 'Rishu start nahi ho paaya' : 'Rishu jaag raha hai…',
                  style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: RishuColors.text),
                ),
                const SizedBox(height: 10),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 560),
                  child: Text(
                    failed
                        ? controller.bootError
                        : 'Pehli baar kholne par thoda time lag sakta hai. Version $appVersion',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: RishuColors.muted, height: 1.5),
                  ),
                ),
                if (failed) ...[
                  const SizedBox(height: 22),
                  FilledButton.icon(
                    onPressed: controller.restart,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Dobara try karo'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
