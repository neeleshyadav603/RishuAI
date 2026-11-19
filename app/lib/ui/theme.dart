import 'package:flutter/material.dart';

class RishuColors {
  static const background = Color(0xFF07070F);
  static const panel = Color(0xFF10101C);
  static const panelHigh = Color(0xFF171728);
  static const border = Color(0xFF26263D);
  static const text = Color(0xFFECEBFF);
  static const muted = Color(0xFF9A98C0);
  static const violet = Color(0xFF7C6CFF);
  static const violetDeep = Color(0xFF3B2DB8);
  static const cyan = Color(0xFF3DD6F5);
  static const pink = Color(0xFFFF6BCB);
  static const amber = Color(0xFFFFB547);
  static const green = Color(0xFF3DDC97);
  static const red = Color(0xFFFF5C7A);
}

ThemeData rishuTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: RishuColors.violet,
    brightness: Brightness.dark,
  ).copyWith(
    primary: RishuColors.violet,
    secondary: RishuColors.cyan,
    surface: RishuColors.panel,
    error: RishuColors.red,
  );
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    scaffoldBackgroundColor: RishuColors.background,
    fontFamily: 'Segoe UI',
    fontFamilyFallback: const ['Nirmala UI', 'Mangal', 'Noto Sans Devanagari', 'Roboto'],
    dividerColor: RishuColors.border,
    tooltipTheme: const TooltipThemeData(waitDuration: Duration(milliseconds: 400)),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: RishuColors.panelHigh,
      hintStyle: const TextStyle(color: RishuColors.muted),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: RishuColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: RishuColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: RishuColors.violet, width: 1.5),
      ),
    ),
  );
}

BoxDecoration glass({double radius = 18, Color? tint, bool glow = false}) {
  final base = tint ?? RishuColors.violet;
  return BoxDecoration(
    color: RishuColors.panel.withValues(alpha: 0.88),
    borderRadius: BorderRadius.circular(radius),
    border: Border.all(color: base.withValues(alpha: 0.22)),
    boxShadow: glow
        ? [BoxShadow(color: base.withValues(alpha: 0.18), blurRadius: 24, spreadRadius: 1)]
        : const [],
  );
}
