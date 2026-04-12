"""Pydantic v2 data models for transcript generation.

These models describe both the LLM structured output schema and the
final transcript JSON schema. They are the single source of truth for
field names, types, and validation constraints. Older TypedDict-based
aliases have been removed; consumers should use these models.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from generator.config import MAX_KEY_PHRASES, MIN_KEY_PHRASES

SectionType = Literal[
    "preview_questions",
    "passage",
    "questions_and_answers",
    "key_phrases",
]
Difficulty = Literal["intermediate", "advanced"]
Part = Literal[3, 4]
ChoiceLabel = Literal["A", "B", "C", "D"]


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
    answer: ChoiceLabel

    @property
    def correct_text(self) -> str:
        return getattr(self.choices, self.answer)


class KeyPhrase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    en: str = Field(min_length=1)
    ja: str = Field(min_length=1)


class PassageLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker: str
    text: str


class DialogueLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker: str
    text: str
    pause_ms_after: int = 0


class Segment(BaseModel):
    """A structurally-ordered unit emitted by a section builder.

    Segments carry a provisional trailing pause; ``finalize_section``
    is responsible for converting a sequence of segments into a
    ``Section`` with the section-last-line pause applied.
    """

    model_config = ConfigDict(extra="forbid")

    speaker: str
    text: str
    pause_ms_after: int

    def as_line(self) -> DialogueLine:
        return DialogueLine(
            speaker=self.speaker,
            text=self.text,
            pause_ms_after=self.pause_ms_after,
        )


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SectionType
    lines: List[DialogueLine]


class SpeakerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice: str
    speed: float
    instructions: str


class Dialogue(BaseModel):
    """Full transcript record written to ``transcripts/*.json``.

    Field order matches the on-disk JSON layout so that
    ``model_dump_json`` produces output identical to the legacy
    ``json.dump`` writer.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    slug: str
    part: Part
    difficulty: Difficulty
    speakers: Dict[str, SpeakerConfig]
    questions: List[Question] = Field(min_length=3, max_length=3)
    key_phrases: List[KeyPhrase] = Field(
        min_length=MIN_KEY_PHRASES, max_length=MAX_KEY_PHRASES
    )
    sections: List[Section]


class TranscriptResponse(BaseModel):
    """Schema enforced on the LLM structured output."""

    model_config = ConfigDict(extra="forbid")

    title: str
    slug: Optional[str] = None
    passage: List[PassageLine] = Field(min_length=1)
    questions: List[Question] = Field(min_length=3, max_length=3)
    key_phrases: List[KeyPhrase] = Field(
        min_length=MIN_KEY_PHRASES, max_length=MAX_KEY_PHRASES
    )
