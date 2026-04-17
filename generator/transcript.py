"""TOEIC Part 3 / Part 4 transcript generation.

Calls the OpenAI chat API with a structured-output schema, then
assembles a fully-rendered Dialogue ready for the TTS stage. Inputs
are trusted: the caller (``main.py``) has already validated them at
the CLI boundary.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from generator.config import (
    KEY_PHRASE_MEMORY_DISPLAY_LIMIT,
    MAX_KEY_PHRASES,
    MIN_KEY_PHRASES,
    NARRATOR_ID,
    NARRATOR_VOICE_CONFIG,
    PASSAGE_SPEED,
    SECTION_LAST_LINE_PAUSE_MS,
    SPEAKER_CONFIGS,
    VOICE_POOL,
)
from generator import key_phrase_memory
from generator.difficulty import DIFFICULTY_PROFILES
from generator.prompts.templates import (
    PART3_PASSAGE_SPEC_TEMPLATE,
    PART3_ROLE_HEADER,
    PART4_PASSAGE_SPEC_TEMPLATE,
    PART4_ROLE_HEADER,
    PROMPT_TEMPLATE,
    QUESTIONS_BLOCK,
    TRAP_GUIDANCE_BLOCK,
)
from generator.types import (
    Dialogue,
    KeyPhrase,
    Line,
    Question,
    Section,
    SpeakerConfig,
    TranscriptResponse,
)

QUESTION_PAUSE_MS = 600
CHOICE_PAUSE_MS = 400
ANSWER_WAIT_MS = 2500
ANSWER_REVEAL_PAUSE_MS = 1200
PASSAGE_PAUSE_MS = 450
KEY_PHRASE_PAUSE_MS = 800
KEY_PHRASE_LEAD_PAUSE_MS = 500

_EN_TERMINALS = (".", "!", "?")
_JA_TERMINALS = ("。", ".", "!", "?", "！", "？")


def _ensure_en_terminal(text: str) -> str:
    cleaned = text.strip()
    return cleaned if cleaned.endswith(_EN_TERMINALS) else cleaned + "."


def _ensure_ja_terminal(text: str) -> str:
    cleaned = text.strip()
    return cleaned if cleaned.endswith(_JA_TERMINALS) else cleaned + "。"


def _slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.strip().lower()).strip("_")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _describe_speaker(cfg: Dict[str, Any], ordinal: Optional[int]) -> str:
    noun = "woman" if cfg["gender"] == "female" else "man"
    prefix = ""
    if ordinal is not None:
        prefix = "first " if ordinal == 1 else "second " if ordinal == 2 else f"{ordinal}th "
    return f"a {prefix}{noun} (internal ID: {cfg['id']})"


def _passage_spec_and_example(
    part: int,
    num_speakers: int,
    num_turns: int,
) -> Tuple[str, str, str]:
    configs = SPEAKER_CONFIGS[num_speakers]
    speaker_ids = [s["id"] for s in configs]

    gender_counts: Dict[str, int] = {}
    for c in configs:
        gender_counts[c["gender"]] = gender_counts.get(c["gender"], 0) + 1
    gender_seen: Dict[str, int] = {}
    descriptions: List[str] = []
    for c in configs:
        g = c["gender"]
        gender_seen[g] = gender_seen.get(g, 0) + 1
        ordinal = gender_seen[g] if gender_counts[g] > 1 else None
        descriptions.append(_describe_speaker(c, ordinal))
    speaker_list = ", ".join(descriptions)

    if part == 3:
        passage_spec = PART3_PASSAGE_SPEC_TEMPLATE.format(
            num_speakers=num_speakers,
            speaker_list=speaker_list,
            num_turns=num_turns,
        )
        passage_key_example = (
            f'[{{"speaker": "{speaker_ids[0]}", "text": "..."}}, '
            f'{{"speaker": "{speaker_ids[1]}", "text": "..."}}]'
        )
        role_header = PART3_ROLE_HEADER
    else:
        passage_spec = PART4_PASSAGE_SPEC_TEMPLATE.format(
            speaker_id=speaker_ids[0],
            num_turns=num_turns,
        )
        passage_key_example = (
            f'[{{"speaker": "{speaker_ids[0]}", "text": "..."}}, '
            f'{{"speaker": "{speaker_ids[0]}", "text": "..."}}]'
        )
        role_header = PART4_ROLE_HEADER
    return role_header, passage_spec, passage_key_example


def _format_recent_phrases_block(phrases: List[str]) -> str:
    if not phrases:
        return ""
    bullets = "\n".join(f"  - {p}" for p in phrases)
    return (
        "\nDIVERSITY CONTEXT:\n"
        "The following key phrases have been used in recent sessions. "
        "Where the passage and context allow naturally, prefer different "
        "expressions. Do not force uncommon vocabulary just to avoid these:\n"
        f"{bullets}\n"
    )


def build_prompt(
    part: int,
    difficulty: str,
    topic: str,
    num_speakers: int,
    num_turns: int,
) -> str:
    role_header, passage_spec, passage_key_example = _passage_spec_and_example(
        part, num_speakers, num_turns
    )
    profile = DIFFICULTY_PROFILES[difficulty]
    recent_phrases = key_phrase_memory.load_recent_phrases(
        difficulty, part, limit=KEY_PHRASE_MEMORY_DISPLAY_LIMIT
    )

    return PROMPT_TEMPLATE.format(
        role_header=role_header,
        part=part,
        topic=topic,
        difficulty_passage_language=profile.passage_language,
        difficulty_information_density=profile.information_density,
        difficulty_question_abstraction=profile.question_abstraction,
        difficulty_distractor_subtlety=profile.distractor_subtlety,
        passage_spec=passage_spec,
        questions_block=QUESTIONS_BLOCK,
        trap_block=TRAP_GUIDANCE_BLOCK,
        min_key_phrases=MIN_KEY_PHRASES,
        max_key_phrases=MAX_KEY_PHRASES,
        passage_key_example=passage_key_example,
        recent_phrases_block=_format_recent_phrases_block(recent_phrases),
    )


# ---------------------------------------------------------------------------
# Voice assignment
# ---------------------------------------------------------------------------


def _assign_voices(num_speakers: int) -> Dict[str, SpeakerConfig]:
    configs = SPEAKER_CONFIGS[num_speakers]
    used: Dict[str, List[int]] = {"female": [], "male": []}
    speakers: Dict[str, SpeakerConfig] = {}

    for cfg in configs:
        gender = cfg["gender"]
        pool = VOICE_POOL[gender]
        available = [i for i in range(len(pool)) if i not in used[gender]]
        idx = random.choice(available)
        used[gender].append(idx)

        voice_cfg = pool[idx]
        speakers[cfg["id"]] = SpeakerConfig(
            voice=voice_cfg["voice"],
            speed=PASSAGE_SPEED,
            instructions=voice_cfg["instructions"],
        )

    speakers[NARRATOR_ID] = SpeakerConfig(**NARRATOR_VOICE_CONFIG)
    return speakers


# ---------------------------------------------------------------------------
# Section assembly
# ---------------------------------------------------------------------------


def _format_question_stem(q: Question) -> str:
    return f"Question {q.id}. {q.text}"


def _format_choice(label: str, choice_text: str) -> str:
    return f"({label}) {choice_text}"


def _format_answer(q: Question) -> str:
    return f"({q.answer}) {_ensure_en_terminal(q.correct_text)}"


def _format_key_phrase(kp: KeyPhrase) -> str:
    return f"{_ensure_en_terminal(kp.en)} {_ensure_ja_terminal(kp.ja)}"


def _section(section_type: str, lines: List[Line], *, final: bool = False) -> Section:
    """Build a Section, overriding the last line's trailing pause with the
    section-last-line pause (0 when this is the terminating section)."""
    if not lines:
        return Section(type=section_type, lines=[])
    last_pause = 0 if final else SECTION_LAST_LINE_PAUSE_MS
    lines[-1] = lines[-1].model_copy(update={"pause_ms_after": last_pause})
    return Section(type=section_type, lines=lines)


def _build_sections(
    passage: List[Line],
    questions: List[Question],
    key_phrases: List[KeyPhrase],
) -> List[Section]:
    preview = [
        Line(speaker=NARRATOR_ID, text=_format_question_stem(q), pause_ms_after=QUESTION_PAUSE_MS)
        for q in questions
    ]

    passage_lines = [
        Line(speaker=line.speaker, text=line.text, pause_ms_after=PASSAGE_PAUSE_MS)
        for line in passage
    ]

    qa_lines: List[Line] = []
    for q in questions:
        qa_lines.append(
            Line(speaker=NARRATOR_ID, text=_format_question_stem(q), pause_ms_after=CHOICE_PAUSE_MS)
        )
        for label in ("A", "B", "C"):
            qa_lines.append(
                Line(
                    speaker=NARRATOR_ID,
                    text=_format_choice(label, getattr(q.choices, label)),
                    pause_ms_after=CHOICE_PAUSE_MS,
                )
            )
        qa_lines.append(
            Line(
                speaker=NARRATOR_ID,
                text=_format_choice("D", q.choices.D),
                pause_ms_after=ANSWER_WAIT_MS,
            )
        )
        qa_lines.append(
            Line(speaker=NARRATOR_ID, text=_format_answer(q), pause_ms_after=ANSWER_REVEAL_PAUSE_MS)
        )

    kp_lines = [
        Line(
            speaker=NARRATOR_ID,
            text="Key phrases.",
            pause_ms_after=KEY_PHRASE_LEAD_PAUSE_MS,
        )
    ]
    kp_lines.extend(
        Line(speaker=NARRATOR_ID, text=_format_key_phrase(kp), pause_ms_after=KEY_PHRASE_PAUSE_MS)
        for kp in key_phrases
    )

    return [
        _section("preview_questions", preview),
        _section("passage", passage_lines),
        _section("questions_and_answers", qa_lines),
        _section("key_phrases", kp_lines, final=True),
    ]


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def generate_dialogue(
    client: OpenAI,
    *,
    model: str,
    topic: str,
    part: int,
    difficulty: str,
    num_speakers: int,
    num_turns: int,
) -> Dialogue:
    """Call the LLM and assemble a fully-rendered Dialogue."""
    prompt = build_prompt(part, difficulty, topic, num_speakers, num_turns)

    completion = client.chat.completions.parse(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        response_format=TranscriptResponse,
    )
    parsed = completion.choices[0].message.parsed

    key_phrase_memory.append_phrases(
        difficulty, part, (kp.en for kp in parsed.key_phrases)
    )

    speakers = _assign_voices(num_speakers)
    sections = _build_sections(parsed.passage, parsed.questions, parsed.key_phrases)

    return Dialogue(
        title=parsed.title,
        slug=_slugify(parsed.title),
        part=part,
        difficulty=difficulty,
        speakers=speakers,
        questions=parsed.questions,
        sections=sections,
    )


def save_dialogue(data: Dialogue, outdir: Path) -> Path:
    """Write a Dialogue to a JSON file, picking a non-colliding filename."""
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / f"{data.slug}.json"
    counter = 1
    while out_path.exists():
        out_path = outdir / f"{data.slug}_{counter}.json"
        counter += 1

    out_path.write_text(
        data.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    return out_path
