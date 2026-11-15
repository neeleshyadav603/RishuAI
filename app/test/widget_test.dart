import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rishu/main.dart';

void main() {
  testWidgets('home shows the orb and the name', (tester) async {
    await tester.pumpWidget(const RishuApp());
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Rishu'), findsOneWidget);
    expect(find.byType(CustomPaint), findsWidgets);
  });
}
