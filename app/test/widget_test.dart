import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rishu/core/connection.dart';
import 'package:rishu/main.dart';
import 'package:rishu/state/assistant.dart';
import 'package:rishu/ui/markdown.dart';

class FakeCore implements CoreConnection {
  final controller = StreamController<Map<String, dynamic>>.broadcast();
  final sent = <Map<String, dynamic>>[];
  final requests = <String>[];

  @override
  Stream<Map<String, dynamic>> get events => controller.stream;

  @override
  void send(Map<String, dynamic> event) => sent.add(event);

  @override
  Future<Map<String, dynamic>> request(String method, String path, [Map<String, dynamic>? body]) async {
    requests.add('$method $path');
    if (path.startsWith('/v1/settings')) return {'settings': {'user_name': 'Neelesh', 'language': 'hinglish'}};
    if (path.startsWith('/v1/activity')) return {'entries': []};
    if (path.startsWith('/v1/voice')) return {'input': true, 'output': true};
    return {};
  }

  @override
  Future<void> close() async {}
}

Map<String, dynamic> hello({bool configured = true, String name = 'Neelesh'}) => {
      'v': 1,
      'type': 'hello',
      'protocol': 1,
      'version': '0.1.0',
      'settings': {
        'user_name': name,
        'language': 'hinglish',
        'script': 'roman',
        'autonomy': 'smart',
        'speak_replies': true,
        'voice_gender': 'male',
      },
      'providers': [
        {'name': 'groq', 'label': 'Groq', 'local': false, 'configured': configured, 'key_url': ''},
      ],
      'capabilities': {
        'step_up': false,
        'approval_timeout_seconds': 120,
        'voice': {'input': true, 'output': true, 'input_reason': '', 'hotkey': ''},
      },
    };

Future<(AssistantController, FakeCore)> started({bool configured = true, String name = 'Neelesh'}) async {
  final core = FakeCore();
  final controller = AssistantController(connector: () async => core);
  await controller.boot();
  core.controller.add(hello(configured: configured, name: name));
  await Future<void>.delayed(Duration.zero);
  return (controller, core);
}

void main() {
  test('a turn streams into one bubble with steps, sources and approval', () async {
    final (c, core) = await started();
    expect(c.phase, Phase.ready);
    c.sendText('AI news search karo');
    expect(core.sent.last, {'type': 'user_message', 'text': 'AI news search karo'});
    for (final e in [
      {'type': 'state_change', 'state': 'thinking'},
      {'type': 'assistant_token', 'text': 'Dhoondh '},
      {'type': 'assistant_token', 'text': '', 'reset': true},
      {'type': 'tool_progress', 'call_id': 'c1', 'tool': 'web_search', 'status': 'started', 'message': 'Searching'},
      {'type': 'tool_result', 'call_id': 'c1', 'tool': 'web_search', 'ok': true, 'summary': 'ok'},
      {
        'type': 'card',
        'card': 'sources',
        'data': {
          'items': [
            {'title': 'AI today', 'url': 'https://example.com/a'},
            {'title': 'bad', 'url': 'javascript:alert(1)'},
          ],
        },
      },
      {'type': 'assistant_token', 'text': 'Yeh '},
      {'type': 'assistant_token', 'text': 'rahi news.'},
      {'type': 'assistant_message', 'text': 'Yeh rahi news.', 'provider': 'groq'},
      {'type': 'tool_call_proposed', 'call_id': 'c2', 'tool': 'send', 'args': {}, 'risk': 'R2', 'decision': 'confirm', 'preview': 'Send hi'},
    ]) {
      core.controller.add({'v': 1, ...e});
    }
    await Future<void>.delayed(Duration.zero);
    final kinds = c.items.map((i) => i.runtimeType.toString()).toList();
    expect(kinds, ['UserItem', 'ToolItem', 'SourcesItem', 'AssistantItem', 'ApprovalItem']);
    expect((c.items[1] as ToolItem).status, ToolStatus.done);
    expect((c.items[2] as SourcesItem).sources.length, 1);
    final reply = c.items[3] as AssistantItem;
    expect(reply.text, 'Yeh rahi news.');
    expect(reply.streaming, isFalse);
    final card = c.items[4] as ApprovalItem;
    c.answer(card, false);
    expect(core.sent.last, {'type': 'approval_response', 'call_id': 'c2', 'approved': false});
    expect(card.status, ApprovalStatus.denied);
  });

  test('voice: listen, transcript, level and stop', () async {
    final (c, core) = await started();
    c.toggleListening();
    expect(core.sent.last, {'type': 'listen_start'});
    core.controller.add({'v': 1, 'type': 'state_change', 'state': 'listening'});
    core.controller.add({'v': 1, 'type': 'audio_level', 'level': 0.7});
    await Future<void>.delayed(Duration.zero);
    expect(c.listening, isTrue);
    expect(c.level, 0.7);
    c.toggleListening();
    expect(core.sent.last, {'type': 'listen_stop'});
    core.controller.add({'v': 1, 'type': 'transcript_final', 'text': 'क्रोम खोलो'});
    core.controller.add({'v': 1, 'type': 'state_change', 'state': 'speaking'});
    await Future<void>.delayed(Duration.zero);
    expect((c.items.single as UserItem).voice, isTrue);
    expect(c.canStop, isTrue);
    c.stop();
    expect(core.sent.last, {'type': 'stop'});
  });

  test('first run without a key opens onboarding', () async {
    final (c, _) = await started(configured: false, name: '');
    expect(c.phase, Phase.onboarding);
    c.finishOnboarding(skipped: true);
    expect(c.phase, Phase.ready);
  });

  test('markdown blocks', () {
    final blocks = parseBlocks('# Title\n\nSome **bold** text\n- one\n- two\n1. first\n```\ncode\n```');
    expect(blocks.map((b) => b.kind).toList(),
        [MdKind.heading, MdKind.paragraph, MdKind.bullet, MdKind.bullet, MdKind.number, MdKind.code]);
    expect(blocks.last.text, 'code');
  });

  testWidgets('home shows the conversation and the composer', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final core = FakeCore();
    final controller = AssistantController(connector: () async => core);
    await tester.runAsync(() async {
      await controller.boot();
      core.controller.add(hello());
      await Future<void>.delayed(const Duration(milliseconds: 10));
    });
    await tester.pumpWidget(RishuApp(controller: controller));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.textContaining('Namaste, Neelesh'), findsOneWidget);
    await tester.tap(find.text('Chrome kholo'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(core.sent.last, {'type': 'user_message', 'text': 'Chrome kholo'});
    controller.handleEvent({'v': 1, 'type': 'assistant_message', 'text': 'Chrome khol diya!'});
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.textContaining('Chrome khol diya!'), findsOneWidget);
    expect(find.byIcon(Icons.mic_rounded), findsWidgets);
  });

  testWidgets('boot failure shows a retry button', (tester) async {
    final controller = AssistantController(connector: () async => throw CoreStartException('core missing'));
    await tester.runAsync(controller.boot);
    await tester.pumpWidget(RishuApp(controller: controller));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('core missing'), findsOneWidget);
    expect(find.text('Dobara try karo'), findsOneWidget);
  });
}
