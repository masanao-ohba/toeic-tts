"""Central configuration constants for the TOEIC TTS pipeline.

Single source of truth for pause durations, voice presets, model defaults,
and valid parameter values. Do not import other generator modules here
to avoid circular imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Section ordering and pauses
# ---------------------------------------------------------------------------

SECTION_ORDER: Tuple[str, ...] = (
    "preview_questions",
    "passage",
    "questions_with_choices",
    "answers",
    "key_phrases",
)

# Section-level pause lengths (ms). Single source of truth.
SHORT_PAUSE_MS = 1500
LONG_PAUSE_MS = 8000

# Pause inserted AFTER each section. The pause before "answers" is the long
# pause; "key_phrases" terminates the file and has no trailing pause.
SECTION_TRAILING_PAUSE_MS: Dict[str, int] = {
    "preview_questions": SHORT_PAUSE_MS,
    "passage": SHORT_PAUSE_MS,
    "questions_with_choices": LONG_PAUSE_MS,
    "answers": SHORT_PAUSE_MS,
    "key_phrases": 0,
}

# Intra-section pause defaults (ms).
QUESTION_PAUSE_MS = 600
CHOICE_PAUSE_MS = 400
ANSWER_PAUSE_MS = 700
PASSAGE_PAUSE_MS = 450
KEY_PHRASE_PAUSE_MS = 800
KEY_PHRASE_LEAD_PAUSE_MS = 500

# Terminal pause at the end of every non-final section (inside the lines
# list itself); the section-boundary pause is applied on top by the TTS
# orchestrator.
SECTION_LAST_LINE_PAUSE_MS = 300

# ---------------------------------------------------------------------------
# Key phrases / questions / parts
# ---------------------------------------------------------------------------

MIN_KEY_PHRASES = 3
MAX_KEY_PHRASES = 8

VALID_PARTS: Tuple[int, ...] = (3, 4)
VALID_DIFFICULTIES: Tuple[str, ...] = ("intermediate", "advanced")
DEFAULT_DIFFICULTY = "intermediate"

VALID_TTS_FORMATS: Tuple[str, ...] = ("wav", "mp3")
VALID_MP3_BITRATES: Tuple[str, ...] = ("128k", "256k")

# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_OUTPUT_FORMAT = "mp3"
DEFAULT_TTS_MP3_BITRATE = "128k"
DEFAULT_TTS_SPEED = 0.97

# ---------------------------------------------------------------------------
# Output directories
# ---------------------------------------------------------------------------

DEFAULT_TRANSCRIPT_DIR = Path("transcripts")
DEFAULT_AUDIO_DIR = Path("output")

# ---------------------------------------------------------------------------
# Number words (1..10) for spoken answer announcements
# ---------------------------------------------------------------------------

NUMBER_WORDS: Dict[int, str] = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}

# ---------------------------------------------------------------------------
# Voice presets
# ---------------------------------------------------------------------------

NARRATOR_ID = "N"

NARRATOR_VOICE_CONFIG: Dict[str, Any] = {
    "voice": "ash",
    "speed": 1.03,
    "instructions": (
        "Neutral TOEIC test narrator. Clear, steady, and authoritative. "
        "Read questions and answers precisely. Do not add extra words."
    ),
}

VOICE_POOL: Dict[str, List[Dict[str, Any]]] = {
    "female": [
        {"voice": "marin", "instructions": "Female speaker. Clear, steady, and engaged."},
        {"voice": "nova", "instructions": "Female speaker. Clear, steady, and engaged."},
        {"voice": "shimmer", "instructions": "Female speaker. Clear, steady, and engaged."},
        {"voice": "coral", "instructions": "Female speaker. Clear, steady, and engaged."},
    ],
    "male": [
        {"voice": "cedar", "instructions": "Male speaker. Clear, steady, and engaged."},
        {"voice": "ash", "instructions": "Male speaker. Clear, steady, and engaged."},
        {"voice": "echo", "instructions": "Male speaker. Clear, steady, and engaged."},
        {"voice": "onyx", "instructions": "Male speaker. Clear, steady, and engaged."},
    ],
}

PASSAGE_SPEAKER_SPEED = 1.03

PASSAGE_CAST_PROMPT = (
    "You are one of several people in a professionally-recorded spoken "
    "conversation for an English listening test. Speak your line with clear, "
    "confident, conversational delivery — audibly projected as if being "
    "recorded for a listener — at the same steady pace as the other "
    "participants. Do not add extra words, labels, or sound effects."
)

SPEAKER_CONFIGS: Dict[int, List[Dict[str, Any]]] = {
    1: [
        {"id": "S", "gender": "male", "speed": PASSAGE_SPEAKER_SPEED},
    ],
    2: [
        {"id": "W", "gender": "female", "speed": PASSAGE_SPEAKER_SPEED},
        {"id": "M", "gender": "male", "speed": PASSAGE_SPEAKER_SPEED},
    ],
    3: [
        {"id": "W1", "gender": "female", "speed": PASSAGE_SPEAKER_SPEED},
        {"id": "M", "gender": "male", "speed": PASSAGE_SPEAKER_SPEED},
        {"id": "W2", "gender": "female", "speed": PASSAGE_SPEAKER_SPEED},
    ],
}

# ---------------------------------------------------------------------------
# Defaults for transcript generation
# ---------------------------------------------------------------------------

DEFAULT_TURNS_PART3 = 8
DEFAULT_TURNS_PART4 = 6
