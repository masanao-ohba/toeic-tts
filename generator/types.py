"""Pydantic models for the TOEIC transcript pipeline.

Two models live here:

- ``TranscriptResponse`` — the schema the LLM structured output is
  parsed into. Its shape matches exactly what we ask the model for.
- ``Dialogue`` — the on-disk JSON record written under ``work/`` and
  consumed by ``generator.tts``. It embeds speaker voice metadata and
  the fully-rendered ``sections[]`` audio layout.

Both models share ``Question`` / ``KeyPhrase`` leaf models. We
deliberately do not use ``Literal`` to constrain enums here: input
validation happens once at the CLI boundary (argparse choices) and
downstream code trusts the values it receives.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field


class ChoiceSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    A: str
    B: str
    C: str
    D: str


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    text: str
    choices: ChoiceSet
    answer: str

    @property
    def correct_text(self) -> str:
        return getattr(self.choices, self.answer)


class KeyPhrase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    en: str
    ja: str


class Line(BaseModel):
    """A single speakable line. Used both for raw LLM passage lines and
    for fully-rendered transcript lines. ``pause_ms_after`` is 0 for
    raw passage lines and filled in by ``build_sections``."""

    model_config = ConfigDict(extra="forbid")

    speaker: str
    text: str
    pause_ms_after: int = 0


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    lines: List[Line]


class SpeakerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice: str
    speed: float
    instructions: str


class TranscriptResponse(BaseModel):
    """What the LLM returns."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    passage: List[Line]
    questions: List[Question]
    key_phrases: List[KeyPhrase]


class Dialogue(BaseModel):
    """Full transcript record written to ``work/<slug>.json``."""

    model_config = ConfigDict(extra="forbid")

    title: str
    slug: str
    part: int
    difficulty: str
    speakers: Dict[str, SpeakerConfig]
    questions: List[Question]
    sections: List[Section]
