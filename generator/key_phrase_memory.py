"""Persistence for previously-adopted key phrases.

Stores key phrases that have been adopted in past generations so that a
subsequent prompt can nudge the LLM toward different expressions, keeping
repeated runs from collapsing onto the same handful of phrases.

Storage layout
--------------
Files are keyed by ``(part, difficulty)`` and live at:

    work/key_phrase_memory/{part}/{difficulty}.json

Each file is a JSON object of the form::

    {
      "schema_version": 1,
      "part": 3,
      "difficulty": "advanced",
      "entries": [
        {"en": "on short notice", "added_at": "2026-04-16T10:00:00Z"},
        {"en": "mitigate",        "added_at": "2026-04-16T10:05:00Z"}
      ]
    }

Entries are ordered oldest → newest. When the list grows beyond
``KEY_PHRASE_MEMORY_MAX_ENTRIES``, the oldest items are dropped at
append time. There is no TTL — entries are only removed by this size
cap or by explicit file deletion.

Duplicates are collapsed case-insensitively on the ``en`` field at
append time: if a phrase is already present, its position is refreshed
to the tail (most-recent) rather than creating a second entry.

Public API
----------
- ``load_recent_phrases(difficulty, part, limit=50)`` returns the
  most recent ``limit`` phrases (newest first) as a plain list of
  strings. Missing files return an empty list.
- ``append_phrases(difficulty, part, phrases)`` records the given
  phrases as newly adopted. Parent directories are created as needed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from generator.config import DEFAULT_WORK_DIR, KEY_PHRASE_MEMORY_MAX_ENTRIES

SCHEMA_VERSION = 1

_MEMORY_SUBDIR = "key_phrase_memory"


def _memory_path(difficulty: str, part: int) -> Path:
    return DEFAULT_WORK_DIR / _MEMORY_SUBDIR / str(part) / f"{difficulty}.json"


def _read_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _entries(data: dict) -> List[dict]:
    raw = data.get("entries", [])
    return [e for e in raw if isinstance(e, dict) and isinstance(e.get("en"), str)]


def load_recent_phrases(difficulty: str, part: int, limit: int = 50) -> List[str]:
    """Return up to ``limit`` most-recent key phrases, newest first.

    Missing file or malformed JSON yields an empty list.
    """
    if limit <= 0:
        return []
    data = _read_file(_memory_path(difficulty, part))
    entries = _entries(data)
    recent = entries[-limit:]
    recent.reverse()
    return [e["en"] for e in recent]


def append_phrases(difficulty: str, part: int, phrases: Iterable[str]) -> None:
    """Append newly-adopted phrases to the persisted memory.

    Case-insensitive duplicates are collapsed — existing matches are
    moved to the tail rather than duplicated. Total stored entries are
    capped at ``KEY_PHRASE_MEMORY_MAX_ENTRIES`` by dropping the oldest.
    """
    cleaned: List[str] = []
    seen_local: set[str] = set()
    for raw in phrases:
        if not isinstance(raw, str):
            continue
        phrase = raw.strip()
        if not phrase:
            continue
        key = phrase.lower()
        if key in seen_local:
            continue
        seen_local.add(key)
        cleaned.append(phrase)

    if not cleaned:
        return

    path = _memory_path(difficulty, part)
    data = _read_file(path)
    entries = _entries(data)

    existing_keys = {e["en"].lower(): i for i, e in enumerate(entries)}
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    seen_keys = {k.lower() for k in cleaned}
    to_remove = sorted(
        {existing_keys[k] for k in seen_keys if k in existing_keys},
        reverse=True,
    )
    for idx in to_remove:
        entries.pop(idx)

    for phrase in cleaned:
        entries.append({"en": phrase, "added_at": now_iso})

    if len(entries) > KEY_PHRASE_MEMORY_MAX_ENTRIES:
        entries = entries[-KEY_PHRASE_MEMORY_MAX_ENTRIES:]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "part": part,
        "difficulty": difficulty,
        "entries": entries,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
