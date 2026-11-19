// A small markdown renderer for replies: headings, lists, bold, inline code,
// code blocks and links. Enough for explanations without extra packages.
import 'package:flutter/material.dart';

import 'theme.dart';

class MarkdownText extends StatelessWidget {
  const MarkdownText(this.text, {super.key, this.style});
  final String text;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final base = style ?? const TextStyle(fontSize: 15, height: 1.5, color: RishuColors.text);
    final blocks = parseBlocks(text);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < blocks.length; i++)
          Padding(
            padding: EdgeInsets.only(top: i == 0 ? 0 : 6),
            child: _block(blocks[i], base),
          ),
      ],
    );
  }

  Widget _block(MdBlock b, TextStyle base) {
    switch (b.kind) {
      case MdKind.heading:
        return Text.rich(
          TextSpan(children: inlineSpans(b.text, base.copyWith(fontWeight: FontWeight.w700, fontSize: b.level <= 2 ? 18 : 16))),
        );
      case MdKind.code:
        return Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF0B0B16),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: RishuColors.border),
          ),
          child: Text(b.text, style: base.copyWith(fontFamily: 'Consolas', fontSize: 13.5, height: 1.4)),
        );
      case MdKind.bullet:
      case MdKind.number:
        return Padding(
          padding: EdgeInsets.only(left: 6.0 + b.level * 14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 22,
                child: Text(
                  b.kind == MdKind.bullet ? '•' : b.marker,
                  style: base.copyWith(color: RishuColors.violet, fontWeight: FontWeight.w700),
                ),
              ),
              Expanded(child: Text.rich(TextSpan(children: inlineSpans(b.text, base)))),
            ],
          ),
        );
      case MdKind.paragraph:
        return Text.rich(TextSpan(children: inlineSpans(b.text, base)));
    }
  }
}

enum MdKind { paragraph, heading, bullet, number, code }

class MdBlock {
  MdBlock(this.kind, this.text, {this.level = 0, this.marker = ''});
  final MdKind kind;
  final String text;
  final int level;
  final String marker;
}

final _heading = RegExp(r'^(#{1,6})\s+(.*)$');
final _bullet = RegExp(r'^(\s*)[-*•]\s+(.*)$');
final _number = RegExp(r'^(\s*)(\d+[.)])\s+(.*)$');

List<MdBlock> parseBlocks(String source) {
  final blocks = <MdBlock>[];
  final lines = source.replaceAll('\r\n', '\n').split('\n');
  final para = <String>[];
  void flush() {
    if (para.isNotEmpty) {
      blocks.add(MdBlock(MdKind.paragraph, para.join(' ').trim()));
      para.clear();
    }
  }

  for (var i = 0; i < lines.length; i++) {
    final line = lines[i];
    if (line.trimLeft().startsWith('```')) {
      flush();
      final code = <String>[];
      i++;
      while (i < lines.length && !lines[i].trimLeft().startsWith('```')) {
        code.add(lines[i]);
        i++;
      }
      blocks.add(MdBlock(MdKind.code, code.join('\n')));
      continue;
    }
    if (line.trim().isEmpty) {
      flush();
      continue;
    }
    final h = _heading.firstMatch(line);
    if (h != null) {
      flush();
      blocks.add(MdBlock(MdKind.heading, h.group(2)!.trim(), level: h.group(1)!.length));
      continue;
    }
    final b = _bullet.firstMatch(line);
    if (b != null) {
      flush();
      blocks.add(MdBlock(MdKind.bullet, b.group(2)!.trim(), level: (b.group(1)!.length / 2).floor().clamp(0, 3)));
      continue;
    }
    final n = _number.firstMatch(line);
    if (n != null) {
      flush();
      blocks.add(MdBlock(MdKind.number, n.group(3)!.trim(),
          level: (n.group(1)!.length / 2).floor().clamp(0, 3), marker: n.group(2)!));
      continue;
    }
    para.add(line.trim());
  }
  flush();
  return blocks;
}

final _inline = RegExp(r'(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*\s][^*]*\*)');

List<InlineSpan> inlineSpans(String text, TextStyle base) {
  final spans = <InlineSpan>[];
  var last = 0;
  for (final m in _inline.allMatches(text)) {
    if (m.start > last) spans.add(TextSpan(text: text.substring(last, m.start), style: base));
    final token = m.group(0)!;
    if (token.startsWith('**') || token.startsWith('__')) {
      spans.add(TextSpan(text: token.substring(2, token.length - 2), style: base.copyWith(fontWeight: FontWeight.w700)));
    } else if (token.startsWith('`')) {
      spans.add(TextSpan(
        text: token.substring(1, token.length - 1),
        style: base.copyWith(
          fontFamily: 'Consolas',
          backgroundColor: const Color(0xFF1E1E33),
          color: const Color(0xFFBFB7FF),
        ),
      ));
    } else if (token.startsWith('[')) {
      final close = token.indexOf('](');
      spans.add(TextSpan(
        text: token.substring(1, close),
        style: base.copyWith(color: RishuColors.cyan, decoration: TextDecoration.underline),
      ));
    } else {
      spans.add(TextSpan(text: token.substring(1, token.length - 1), style: base.copyWith(fontStyle: FontStyle.italic)));
    }
    last = m.end;
  }
  if (last < text.length) spans.add(TextSpan(text: text.substring(last), style: base));
  return spans;
}
