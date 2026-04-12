"""Text formatting helpers for transcript rendering.

Single source of truth for sentence-terminal punctuation and for the
canonical spoken forms used by the TOEIC narrator (question stems,
choice labels, answer announcements, key phrases).
"""

from __future__ import annotations

from generator.config import NUMBER_WORDS
from generator.types import KeyPhrase, Question

EN_TERMINAL: tuple[str, ...] = (".", "!", "?")
JA_TERMINAL: tuple[str, ...] = ("。", ".", "!", "?", "！", "？")

KEY_PHRASES_LEAD_TEXT: str = "Key phrases."


def ensure_en_terminal(text: str) -> str:
    cleaned = text.strip()
    return cleaned if cleaned.endswith(EN_TERMINAL) else cleaned + "."


def ensure_ja_terminal(text: str) -> str:
    cleaned = text.strip()
    return cleaned if cleaned.endswith(JA_TERMINAL) else cleaned + "。"


def format_question_stem(q: Question) -> str:
    return f"Question {q.id}. {q.text}"


def format_choice(label: str, choice_text: str) -> str:
    return f"({label}) {choice_text}"


def format_answer(q: Question) -> str:
    spoken = NUMBER_WORDS.get(q.id, str(q.id))
    return f"Number {spoken}. {ensure_en_terminal(q.correct_text)}"


def format_key_phrase(kp: KeyPhrase) -> str:
    return f"{ensure_en_terminal(kp.en)} {ensure_ja_terminal(kp.ja)}"
