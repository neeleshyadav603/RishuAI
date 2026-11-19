"""Prepare reply text for speech: strip markdown, split into sentences, detect script."""

from __future__ import annotations

import re
import unicodedata

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
_URL = re.compile(r"https?://\S+")
_MARKS = re.compile(r"[*_#>|~]+")
_BULLET = re.compile(r"^\s*(?:[-•]|\d+[.)])\s+", re.MULTILINE)
_SPACES = re.compile(r"[ \t]+")
# Emoji and pictographs are not read aloud.
_EMOJI = re.compile("[\U0001f000-\U0001faff\U00002600-\U000027bf\U0000fe0f\U0000200d]+")
# Sentence ends: . ! ? and the Devanagari danda, followed by space or end.
_SENTENCE_END = re.compile(r"(?<=[.!?।॥])\s+")


def clean_for_speech(text: str) -> str:
    """Remove what should not be read aloud: code, links, markdown marks."""
    text = _CODE_BLOCK.sub(" ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub(" ", text)
    text = _BULLET.sub("", text)
    text = _MARKS.sub(" ", text)
    text = _EMOJI.sub(" ", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    # A line without end punctuation (a heading, a list item) still ends a sentence.
    joined = []
    for line in lines:
        if not line:
            continue
        joined.append(line if line[-1] in ".!?।:;," else line + ".")
    return " ".join(joined).strip()


def split_for_speech(text: str, max_chars: int = 220) -> list[str]:
    """Sentences, merged up to ``max_chars`` so speech starts fast and flows."""
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:  # a very long sentence: cut at a comma or space
            cut = max(sentence.rfind(",", 0, max_chars), sentence.rfind(" ", 0, max_chars))
            end = cut + 1 if cut > 40 else max_chars
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:end].strip())
            sentence = sentence[end:].strip()
        if not sentence:
            continue
        # Keep the first chunk short so the first words are heard quickly.
        limit = 90 if not chunks else max_chars
        if current and len(current) + 1 + len(sentence) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def is_devanagari(text: str) -> bool:
    """True when most letters are Devanagari (Hindi script)."""
    deva = sum(1 for ch in text if "ऀ" <= ch <= "ॿ")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return deva > 0 and deva >= latin


_GOODBYES = {
    "bas",
    "bas karo",
    "bas itna hi",
    "bas itna",
    "theek hai bas",
    "ok bas",
    "okay bas",
    "thank you",
    "thanks",
    "thank you rishu",
    "thanks rishu",
    "dhanyavaad",
    "dhanyawad",
    "shukriya",
    "bye",
    "ok bye",
    "bye rishu",
    "band karo",
    "chup",
    "chup ho jao",
    "बस",
    "बस करो",
    "बस इतना ही",
    "धन्यवाद",
    "शुक्रिया",
    "थैंक यू",
    "बाय",
    "ठीक है बस",
}


def is_goodbye(text: str) -> bool:
    """A short 'that's all' that ends conversation mode instead of starting a turn."""
    # Keep letters, digits and combining marks (Devanagari vowel signs are marks).
    cleaned = "".join(ch if unicodedata.category(ch)[0] in "LMN" else " " for ch in text.lower())
    return " ".join(cleaned.split()) in _GOODBYES
