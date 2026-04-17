"""Central constants for the TOEIC TTS pipeline.

Only values that appear in more than one place, or that define the
fixed audio layout spec, live here. Single-use constants are kept
next to their call site.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Audio layout — section order and boundary pauses
# ---------------------------------------------------------------------------

# Inter-section pauses. The pause after each section is the short pause,
# except "key_phrases" which is the final section and terminates the file.
SHORT_PAUSE_MS = 1500

SECTION_TRAILING_PAUSE_MS: Dict[str, int] = {
    "preview_questions": SHORT_PAUSE_MS,
    "passage": SHORT_PAUSE_MS,
    "questions_and_answers": SHORT_PAUSE_MS,
    "key_phrases": 0,
}

SECTION_LAST_LINE_PAUSE_MS = 300

# ---------------------------------------------------------------------------
# Key phrases count bounds (enforced inside the LLM prompt)
# ---------------------------------------------------------------------------

MIN_KEY_PHRASES = 3
MAX_KEY_PHRASES = 8

# ---------------------------------------------------------------------------
# Key phrase memory tuning
# ---------------------------------------------------------------------------

KEY_PHRASE_MEMORY_DISPLAY_LIMIT = 15
KEY_PHRASE_MEMORY_MAX_ENTRIES = 500

# ---------------------------------------------------------------------------
# Output directories
# ---------------------------------------------------------------------------

DEFAULT_AUDIO_DIR = Path("output")
DEFAULT_WORK_DIR = Path("work")

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

PASSAGE_CAST_PROMPT = (
    "You are one of several people in a professionally-recorded spoken "
    "conversation for an English listening test. Speak your line with clear, "
    "confident, conversational delivery — audibly projected as if being "
    "recorded for a listener — at the same steady pace as the other "
    "participants. Do not add extra words, labels, or sound effects."
)

SPEAKER_CONFIGS: Dict[int, List[Dict[str, Any]]] = {
    1: [
        {"id": "S", "gender": "male"},
    ],
    2: [
        {"id": "W", "gender": "female"},
        {"id": "M", "gender": "male"},
    ],
    3: [
        {"id": "W1", "gender": "female"},
        {"id": "M", "gender": "male"},
        {"id": "W2", "gender": "female"},
    ],
}

PASSAGE_SPEED = 1.03
