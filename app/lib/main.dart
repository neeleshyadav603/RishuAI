// Rishu app shell. This first version proves the Windows and Android build
// pipeline: it shows the animated orb and the build version. The conversation
// UI and the link to the core arrive in Phase 2 (see docs/PROGRESS.md).
import 'dart:math' as math;

import 'package:flutter/material.dart';

const String appVersion = String.fromEnvironment('RISHU_VERSION', defaultValue: 'dev');

void main() => runApp(const RishuApp());

class RishuApp extends StatelessWidget {
  const RishuApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Rishu',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6C5CE7),
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xFF0B0B14),
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 6),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              SizedBox(
                width: 240,
                height: 240,
                child: AnimatedBuilder(
                  animation: _controller,
                  builder: (context, child) => CustomPaint(painter: OrbPainter(_controller.value)),
                ),
              ),
              const SizedBox(height: 32),
              Text('Rishu', style: textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              Text('Aapka personal AI assistant', style: textTheme.titleMedium),
              const SizedBox(height: 24),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 32),
                child: Text(
                  'Build $appVersion. Yeh pehla build sirf app ka dhaancha hai; '
                  'baat-cheet aur kaam karne wale features agle builds mein aa rahe hain.',
                  textAlign: TextAlign.center,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The orb: a soft glow, a pulsing core and three slowly rotating rings.
class OrbPainter extends CustomPainter {
  OrbPainter(this.t);

  /// Animation progress from 0 to 1.
  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final base = size.shortestSide / 2;
    final pulse = 0.94 + 0.06 * math.sin(t * 2 * math.pi * 3);

    final glow = Paint()
      ..shader = const RadialGradient(
        colors: [Color(0x886C5CE7), Color(0x006C5CE7)],
      ).createShader(Rect.fromCircle(center: center, radius: base));
    canvas.drawCircle(center, base, glow);

    final coreRadius = base * 0.55 * pulse;
    final core = Paint()
      ..shader = const RadialGradient(
        center: Alignment(-0.3, -0.4),
        colors: [Color(0xFFB8AEFF), Color(0xFF6C5CE7), Color(0xFF2D1E8F)],
        stops: [0.0, 0.55, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: coreRadius));
    canvas.drawCircle(center, coreRadius, core);

    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = const Color(0x66B8AEFF);
    for (var i = 0; i < 3; i++) {
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(t * 2 * math.pi + i * math.pi / 3);
      canvas.drawOval(
        Rect.fromCenter(center: Offset.zero, width: base * 1.7, height: base * (0.8 + 0.2 * i)),
        ring,
      );
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(OrbPainter oldDelegate) => oldDelegate.t != t;
}
