// The orb: Rishu's face. Colour, motion and size follow what Rishu is doing,
// and while listening it breathes with the user's voice.
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../state/assistant.dart';
import 'theme.dart';

class OrbPalette {
  const OrbPalette(this.core, this.edge, this.glow, this.speed);
  final Color core;
  final Color edge;
  final Color glow;
  final double speed;

  static OrbPalette of(OrbMood mood) => switch (mood) {
        OrbMood.listening => const OrbPalette(Color(0xFFB8F4FF), RishuColors.cyan, RishuColors.cyan, 1.6),
        OrbMood.thinking => const OrbPalette(Color(0xFFD4CCFF), RishuColors.violet, RishuColors.violet, 2.6),
        OrbMood.acting => const OrbPalette(Color(0xFFFFE2B0), RishuColors.amber, RishuColors.amber, 2.2),
        OrbMood.speaking => const OrbPalette(Color(0xFFFFD0F0), RishuColors.pink, RishuColors.pink, 1.8),
        OrbMood.offline => const OrbPalette(Color(0xFF8E8EA8), Color(0xFF4A4A63), Color(0xFF3A3A52), 0.4),
        OrbMood.locked => const OrbPalette(Color(0xFF8E8EA8), Color(0xFF4A4A63), Color(0xFF3A3A52), 0.4),
        OrbMood.connecting => const OrbPalette(Color(0xFFB9B4E6), Color(0xFF5B52A8), Color(0xFF5B52A8), 1.0),
        OrbMood.idle => const OrbPalette(Color(0xFFC9C2FF), RishuColors.violet, RishuColors.violetDeep, 0.8),
      };
}

class Orb extends StatefulWidget {
  const Orb({super.key, required this.mood, this.level = 0, this.size = 220});
  final OrbMood mood;
  final double level;
  final double size;

  @override
  State<Orb> createState() => _OrbState();
}

class _OrbState extends State<Orb> with SingleTickerProviderStateMixin {
  late final AnimationController _clock = AnimationController(vsync: this, duration: const Duration(seconds: 60))
    ..repeat();
  double _phase = 0;
  double _lastT = 0;
  double _level = 0;
  OrbPalette _from = OrbPalette.of(OrbMood.connecting);
  OrbPalette _to = OrbPalette.of(OrbMood.connecting);
  double _blend = 1;

  @override
  void initState() {
    super.initState();
    _to = OrbPalette.of(widget.mood);
    _from = _to;
  }

  @override
  void didUpdateWidget(Orb old) {
    super.didUpdateWidget(old);
    if (old.mood != widget.mood) {
      _from = _current();
      _to = OrbPalette.of(widget.mood);
      _blend = 0;
    }
  }

  OrbPalette _current() {
    final t = Curves.easeOut.transform(_blend.clamp(0.0, 1.0));
    return OrbPalette(
      Color.lerp(_from.core, _to.core, t)!,
      Color.lerp(_from.edge, _to.edge, t)!,
      Color.lerp(_from.glow, _to.glow, t)!,
      _from.speed + (_to.speed - _from.speed) * t,
    );
  }

  @override
  void dispose() {
    _clock.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: SizedBox.square(
        dimension: widget.size,
        child: AnimatedBuilder(
          animation: _clock,
          builder: (context, _) {
            final t = _clock.value * 60; // seconds
            var dt = t - _lastT;
            if (dt < 0 || dt > 0.5) dt = 1 / 60;
            _lastT = t;
            _blend = (_blend + dt * 2.5).clamp(0.0, 1.0);
            final palette = _current();
            _phase += dt * palette.speed;
            final target = widget.mood == OrbMood.listening ? widget.level : 0.0;
            _level += (target - _level) * math.min(1.0, dt * 12);
            return CustomPaint(painter: _OrbPainter(_phase, palette, _level, widget.mood));
          },
        ),
      ),
    );
  }
}

class _OrbPainter extends CustomPainter {
  _OrbPainter(this.phase, this.palette, this.level, this.mood);
  final double phase;
  final OrbPalette palette;
  final double level;
  final OrbMood mood;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2;
    final breathe = 1 + 0.035 * math.sin(phase * 1.3);
    final speakingPulse = mood == OrbMood.speaking ? 0.06 * (0.5 + 0.5 * math.sin(phase * 7)) : 0.0;
    final scale = breathe + level * 0.22 + speakingPulse;

    // Outer glow.
    canvas.drawCircle(
      c,
      r,
      Paint()
        ..shader = RadialGradient(colors: [
          palette.glow.withValues(alpha: 0.45 + level * 0.3),
          palette.glow.withValues(alpha: 0.0),
        ]).createShader(Rect.fromCircle(center: c, radius: r)),
    );

    // Ripples while listening or speaking.
    if (mood == OrbMood.listening || mood == OrbMood.speaking) {
      for (var i = 0; i < 3; i++) {
        final p = ((phase * 0.6) + i / 3) % 1.0;
        final rr = r * (0.5 + 0.48 * p) * (1 + level * 0.2);
        canvas.drawCircle(
          c,
          rr,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2
            ..color = palette.edge.withValues(alpha: (1 - p) * 0.5),
        );
      }
    }

    // Orbit rings.
    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    for (var i = 0; i < 3; i++) {
      canvas.save();
      canvas.translate(c.dx, c.dy);
      canvas.rotate(phase * (0.35 + i * 0.12) * (i.isEven ? 1 : -1) + i * math.pi / 3);
      ring.color = palette.edge.withValues(alpha: 0.28 + 0.1 * i);
      canvas.drawOval(
        Rect.fromCenter(center: Offset.zero, width: r * 1.62 * scale, height: r * (0.55 + 0.22 * i) * scale),
        ring,
      );
      canvas.restore();
    }

    // Core with a wobbling, living edge.
    final coreR = r * 0.48 * scale;
    final path = Path();
    const points = 72;
    final wobble = mood == OrbMood.offline ? 0.0 : 0.035 + level * 0.12 + (mood == OrbMood.thinking ? 0.03 : 0);
    for (var i = 0; i <= points; i++) {
      final a = i / points * 2 * math.pi;
      final w = 1 +
          wobble * math.sin(a * 3 + phase * 2.1) +
          wobble * 0.6 * math.sin(a * 5 - phase * 1.7) +
          wobble * 0.4 * math.cos(a * 2 + phase * 3.1);
      final p = c + Offset(math.cos(a), math.sin(a)) * coreR * w;
      if (i == 0) {
        path.moveTo(p.dx, p.dy);
      } else {
        path.lineTo(p.dx, p.dy);
      }
    }
    path.close();
    final rect = Rect.fromCircle(center: c, radius: coreR * 1.2);
    canvas.drawPath(
      path,
      Paint()
        ..shader = RadialGradient(
          center: Alignment(-0.35 + 0.15 * math.sin(phase), -0.45 + 0.1 * math.cos(phase)),
          colors: [palette.core, palette.edge, palette.edge.withValues(alpha: 0.65)],
          stops: const [0.0, 0.6, 1.0],
        ).createShader(rect),
    );

    // Thinking: a bright arc travelling around the core.
    if (mood == OrbMood.thinking || mood == OrbMood.acting || mood == OrbMood.connecting) {
      canvas.drawArc(
        Rect.fromCircle(center: c, radius: coreR * 1.18),
        phase * 2.4,
        math.pi * 0.6,
        false,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round
          ..strokeWidth = 3
          ..shader = SweepGradient(
            colors: [palette.core.withValues(alpha: 0), palette.core],
            transform: GradientRotation(phase * 2.4),
          ).createShader(Rect.fromCircle(center: c, radius: coreR * 1.18)),
      );
    }

    // Highlight.
    canvas.drawCircle(
      c + Offset(-coreR * 0.32, -coreR * 0.38),
      coreR * 0.22,
      Paint()..color = Colors.white.withValues(alpha: 0.18),
    );
  }

  @override
  bool shouldRepaint(_OrbPainter old) => true;
}
