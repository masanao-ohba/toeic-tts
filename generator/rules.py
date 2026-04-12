"""Business rule helpers for TOEIC transcript generation.

Single source of truth for validations and normalizations used by both
``main.py`` and ``generator.transcript``.
"""

from __future__ import annotations

import sys
from typing import Optional

from generator.config import (
    DEFAULT_TURNS_PART3,
    DEFAULT_TURNS_PART4,
    VALID_DIFFICULTIES,
    VALID_PARTS,
)


def validate_part(value: int) -> int:
    if value not in VALID_PARTS:
        raise ValueError(f"part must be one of {VALID_PARTS}, got {value}")
    return value


def validate_difficulty(value: str) -> str:
    if value not in VALID_DIFFICULTIES:
        raise ValueError(
            f"difficulty must be one of {VALID_DIFFICULTIES}, got {value}"
        )
    return value


def normalize_speaker_count(part: int, requested: Optional[int]) -> int:
    """Return the number of passage speakers for the given part.

    Part 4 always forces a single speaker. Part 3 accepts 2 or 3 (default 2).
    Raises ``ValueError`` for invalid Part 3 counts.
    """
    if part == 4:
        return 1
    if requested is None:
        return 2
    if requested in (2, 3):
        return requested
    raise ValueError(f"Part 3 requires 2 or 3 speakers, got {requested}")


def default_turns_for_part(part: int) -> int:
    return DEFAULT_TURNS_PART3 if part == 3 else DEFAULT_TURNS_PART4


def normalize_speaker_count_with_warning(
    part: int, requested: Optional[int]
) -> int:
    """Same as ``normalize_speaker_count`` but emits a stderr warning when
    a Part-4 speaker override is silently ignored (matches legacy main.py
    behaviour)."""
    if part == 4 and requested is not None and requested != 1:
        print(
            f"WARN: Part 4 requires a single speaker; ignoring speakers={requested}",
            file=sys.stderr,
        )
    return normalize_speaker_count(part, requested)
