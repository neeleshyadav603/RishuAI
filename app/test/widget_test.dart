import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rishu/core/connection.dart';
import 'package:rishu/main.dart';
import 'package:rishu/state/assistant.dart';
import 'package:rishu/ui/markdown.dart';
import 'package:rishu/ui/settings.dart';

class FakeCore implements CoreConnection {
  final controller = StreamController<Map<String, dynamic>>.broadcast();
  final sent = <Map<String, dynamic>>[];
  final requests = <String>[];
  final bodies = <Map<String, dynamic>?>[];

  @override
  Stream<Map<String, dynamic>> get events => controller.stream;

  @override
  void send(Map<String, dynamic> event) => sent.add(event);

  @override
  Future<Map<String, dynamic>> request(String method, String path, [Map<String, dynamic>? body]) async {
    requests.add('$method $path');
    bodies.add(body);
    if (path.startsWith('/v1/settings')) return {'settings': {'user_name': 'Neelesh', 'language': 'hinglish'}};
    if (path.startsWith('/v1/activity')) return {'entries': []};
    if (path.startsWith('/v1/voice')) return {'input': true, 'output': true};
    return {};
  }

  @override
  Future<void> close() async {}
}

Map<String, dynamic> hello({bool configured = true, String name = 'Neelesh', bool locked = false}) => {
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
      'lock': {'locked': locked, 'pin_set': locked, 'phrase_set': locked, 'hello': false, 'idle_minutes': 10},
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
    expect(core.sent.single['type'], 'speak'); // the spoken hello, once per launch
    expect('${core.sent.single['text']}', contains('Neelesh'));
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

  test('R3 cards: blocked without step-up, PIN sent with the approval when ready', () async {
    final (c, core) = await started();
    core.controller.add({'v': 1, 'type': 'tool_call_proposed', 'call_id': 'r1', 'tool': 'browser_click', 'args': {},
        'risk': 'R3', 'decision': 'step_up', 'preview': 'Click "Submit"', 'step_up_ready': false});
    core.controller.add({'v': 1, 'type': 'tool_call_proposed', 'call_id': 'r2', 'tool': 'browser_click', 'args': {},
        'risk': 'R3', 'decision': 'step_up', 'preview': 'Click "Submit"', 'step_up_ready': true});
    await Future<void>.delayed(Duration.zero);
    final cards = c.items.whereType<ApprovalItem>().toList();
    expect(cards[0].status, ApprovalStatus.blocked);
    expect(cards[1].status, ApprovalStatus.pending);
    c.answer(cards[1], true, pin: '4826');
    expect(core.sent.last, {'type': 'approval_response', 'call_id': 'r2', 'approved': true, 'pin': '4826'});
  });

  test('teach mode: banner state, done, cancel and forget', () async {
    final (c, core) = await started();
    expect(c.teach.recording, isFalse);
    core.controller.add({'v': 1, 'type': 'teach_state', 'recording': true, 'task': 'assignment marks',
        'steps': ['Type "Priya" into "Search students"'], 'skills': []});
    await Future<void>.delayed(Duration.zero);
    expect(c.teach.recording, isTrue);
    expect(c.teach.steps.single, contains('Priya'));
    c.teachDone();
    expect(core.sent.last['type'], 'user_message');
    c.teachCancel();
    expect(core.sent.last, {'type': 'teach_cancel'});
    core.controller.add({'v': 1, 'type': 'teach_state', 'recording': false, 'steps': [],
        'skills': [{'name': 'LMS marks', 'description': 'Enter marks', 'steps': 4}]});
    await Future<void>.delayed(Duration.zero);
    expect(c.teach.skills.single.name, 'LMS marks');
    c.forgetSkill('LMS marks');
    expect(core.sent.last, {'type': 'forget_skill', 'name': 'LMS marks'});
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

  test('lock state clears the chat and routes unlock errors to the lock screen', () async {
    final (c, core) = await started();
    c.sendText('Mera secret note');
    core.controller.add({'v': 1, 'type': 'lock_state', 'locked': true, 'pin_set': true});
    core.controller.add({'v': 1, 'type': 'error', 'code': 'unlock_wrong', 'message': 'Password match nahi hua.'});
    await Future<void>.delayed(Duration.zero);
    expect(c.locked, isTrue);
    expect(c.items, isEmpty);
    expect(c.lockError, 'Password match nahi hua.');
    c.unlockWithPin('4826');
    expect(core.sent.last, {'type': 'unlock', 'method': 'pin', 'pin': '4826'});
    expect(c.lockError, isEmpty);
    core.controller.add({'v': 1, 'type': 'lock_state', 'locked': false, 'pin_set': true});
    await Future<void>.delayed(Duration.zero);
    expect(c.locked, isFalse);
  });

  testWidgets('a locked Rishu shows the lock screen and unlocks with the PIN', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final core = FakeCore();
    final controller = AssistantController(connector: () async => core);
    await tester.runAsync(() async {
      await controller.boot();
      core.controller.add(hello(locked: true));
      await Future<void>.delayed(const Duration(milliseconds: 10));
    });
    await tester.pumpWidget(RishuApp(controller: controller));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Rishu locked hai'), findsOneWidget);
    expect(find.textContaining('Namaste, Neelesh'), findsNothing);
    expect(find.text('Bolkar unlock'), findsOneWidget);
    await tester.enterText(find.byKey(const ValueKey('lock-pin')), '4826');
    await tester.tap(find.byTooltip('Unlock'));
    await tester.pump();
    expect(core.sent.last, {'type': 'unlock', 'method': 'pin', 'pin': '4826'});
    controller.handleEvent({'v': 1, 'type': 'lock_state', 'locked': false, 'pin_set': true, 'phrase_set': true});
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.textContaining('Namaste, Neelesh'), findsOneWidget);
    expect(find.byKey(const ValueKey('sidebar-lock')), findsOneWidget);
  });

  testWidgets('choosing the personal style saves it with a woman\'s voice and says hello', (tester) async {
    tester.view.physicalSize = const Size(1400, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final core = FakeCore();
    final controller = AssistantController(connector: () async => core);
    await tester.runAsync(() async {
      await controller.boot();
      core.controller.add(hello());
      await Future<void>.delayed(const Duration(milliseconds: 10));
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SettingsScreen(controller: controller))));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Professional'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const ValueKey('persona-personal')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('persona-personal')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(core.bodies.whereType<Map<String, dynamic>>(), anyElement(equals({'persona': 'personal', 'voice_gender': 'female'})));
    expect(core.sent.last['type'], 'speak');
    await tester.ensureVisible(find.byKey(const ValueKey('about-me')));
    await tester.pump();
    await tester.enterText(find.byKey(const ValueKey('about-me')), 'Main GITM mein padhata hoon.');
    await tester.ensureVisible(find.byKey(const ValueKey('save-about-me')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('save-about-me')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(core.bodies.last, {'about_me': 'Main GITM mein padhata hoon.'});
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
