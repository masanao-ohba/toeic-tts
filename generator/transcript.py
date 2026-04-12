#!/usr/bin/env python3
"""
TOEIC Part 3 / Part 4 transcript generator.

Uses OpenAI ChatCompletion to produce either a multi-speaker dialogue
(Part 3) or a single-speaker narration (Part 4), along with three
comprehension questions and four choices each. Output follows the
``sections[]`` schema consumed by ``generator.tts``.

Usage (standalone):
    uv run python -m generator.transcript --part 3 --topic "hotel check-in"
    uv run python -m generator.transcript --part 4 --topic "company announcement" --difficulty advanced
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from generator.config import (
    ANSWER_PAUSE_MS,
    CHOICE_PAUSE_MS,
    DEFAULT_CHAT_MODEL,
    DEFAULT_DIFFICULTY,
    DEFAULT_TRANSCRIPT_DIR,
    DEFAULT_TURNS_PART3,
    DEFAULT_TURNS_PART4,
    KEY_PHRASE_LEAD_PAUSE_MS,
    KEY_PHRASE_PAUSE_MS,
    MAX_KEY_PHRASES,
    MIN_KEY_PHRASES,
    NARRATOR_ID,
    NARRATOR_VOICE_CONFIG,
    PASSAGE_PAUSE_MS,
    QUESTION_PAUSE_MS,
    SECTION_LAST_LINE_PAUSE_MS,
    SPEAKER_CONFIGS,
    VALID_DIFFICULTIES,
    VALID_PARTS,
    VOICE_POOL,
)
from generator.prompts.templates import (
    DIFFICULTY_BLOCKS,
    PART3_PASSAGE_SPEC_TEMPLATE,
    PART3_ROLE_HEADER,
    PART4_PASSAGE_SPEC_TEMPLATE,
    PART4_ROLE_HEADER,
    PROMPT_TEMPLATE,
    QUESTIONS_BLOCK,
    TRAP_GUIDANCE_BLOCK,
)
from generator.rules import (
    default_turns_for_part,
    normalize_speaker_count,
)
from generator.text import (
    KEY_PHRASES_LEAD_TEXT,
    format_answer,
    format_choice,
    format_key_phrase,
    format_question_stem,
)
from generator.types import (
    Dialogue,
    KeyPhrase,
    PassageLine,
    Question,
    Section,
    SectionType,
    Segment,
    SpeakerConfig,
    TranscriptResponse,
)

load_dotenv()


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
) -> tuple:
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


def build_prompt(
    part: int,
    difficulty: str,
    topic: str,
    num_speakers: int,
    num_turns: int,
) -> str:
    """Build a ChatCompletion prompt for TOEIC Part 3 or Part 4 content."""
    if part not in VALID_PARTS:
        raise ValueError(f"part must be one of {VALID_PARTS}, got {part}")
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"difficulty must be one of {VALID_DIFFICULTIES}, got {difficulty}")

    role_header, passage_spec, passage_key_example = _passage_spec_and_example(
        part, num_speakers, num_turns
    )

    return PROMPT_TEMPLATE.format(
        role_header=role_header,
        part=part,
        topic=topic,
        difficulty_block=DIFFICULTY_BLOCKS[difficulty],
        passage_spec=passage_spec,
        questions_block=QUESTIONS_BLOCK,
        trap_block=TRAP_GUIDANCE_BLOCK,
        min_key_phrases=MIN_KEY_PHRASES,
        max_key_phrases=MAX_KEY_PHRASES,
        passage_key_example=passage_key_example,
    )


# ---------------------------------------------------------------------------
# Voice assignment
# ---------------------------------------------------------------------------


def assign_voices(num_speakers: int) -> Dict[str, SpeakerConfig]:
    """Randomly assign TTS voices to each passage speaker.

    The narrator voice is added separately; this function only covers
    the speakers used inside the passage section.
    """
    configs = SPEAKER_CONFIGS[num_speakers]
    used_female: List[int] = []
    used_male: List[int] = []
    speakers: Dict[str, SpeakerConfig] = {}

    for cfg in configs:
        pool = VOICE_POOL[cfg["gender"]]
        used = used_female if cfg["gender"] == "female" else used_male
        available = [i for i in range(len(pool)) if i not in used]
        idx = random.choice(available)
        used.append(idx)

        voice_cfg = pool[idx]
        speakers[cfg["id"]] = SpeakerConfig(
            voice=voice_cfg["voice"],
            speed=float(cfg["speed"]),
            instructions=voice_cfg["instructions"],
        )

    return speakers


# ---------------------------------------------------------------------------
# Section assembly
# ---------------------------------------------------------------------------


def finalize_section(
    section_type: SectionType,
    segments: List[Segment],
    *,
    last_pause_ms: int = SECTION_LAST_LINE_PAUSE_MS,
) -> Section:
    """Materialize a structurally-ordered segment sequence into a Section.

    The last segment's trailing pause is overridden with ``last_pause_ms``
    regardless of what the builder emitted. This centralizes the
    "section terminator" rule so section builders can focus purely on
    structural order.
    """
    if not segments:
        return Section(type=section_type, lines=[])
    *head, last = segments
    lines = [s.as_line() for s in head]
    lines.append(
        last.model_copy(update={"pause_ms_after": last_pause_ms}).as_line()
    )
    return Section(type=section_type, lines=lines)


def _build_preview_questions_section(questions: List[Question]) -> Section:
    segments = [
        Segment(
            speaker=NARRATOR_ID,
            text=format_question_stem(q),
            pause_ms_after=QUESTION_PAUSE_MS,
        )
        for q in questions
    ]
    return finalize_section("preview_questions", segments)


def _build_passage_section(passage_lines: List[PassageLine]) -> Section:
    segments = [
        Segment(
            speaker=line.speaker,
            text=line.text,
            pause_ms_after=PASSAGE_PAUSE_MS,
        )
        for line in passage_lines
    ]
    return finalize_section("passage", segments)


def _build_questions_with_choices_section(
    questions: List[Question],
) -> Section:
    segments: List[Segment] = []
    for q in questions:
        segments.append(
            Segment(
                speaker=NARRATOR_ID,
                text=format_question_stem(q),
                pause_ms_after=CHOICE_PAUSE_MS,
            )
        )
        # Structural rule: A/B/C use the inter-choice pause; D is the
        # transition into the next question stem. The trailing pause of
        # the very last D (last question) is normalized by finalize_section.
        for label in ("A", "B", "C"):
            segments.append(
                Segment(
                    speaker=NARRATOR_ID,
                    text=format_choice(label, getattr(q.choices, label)),
                    pause_ms_after=CHOICE_PAUSE_MS,
                )
            )
        segments.append(
            Segment(
                speaker=NARRATOR_ID,
                text=format_choice("D", q.choices.D),
                pause_ms_after=QUESTION_PAUSE_MS,
            )
        )
    return finalize_section("questions_with_choices", segments)


def _build_answers_section(questions: List[Question]) -> Section:
    segments = [
        Segment(
            speaker=NARRATOR_ID,
            text=format_answer(q),
            pause_ms_after=ANSWER_PAUSE_MS,
        )
        for q in questions
    ]
    return finalize_section("answers", segments)


def _build_key_phrases_section(key_phrases: List[KeyPhrase]) -> Section:
    segments = [
        Segment(
            speaker=NARRATOR_ID,
            text=KEY_PHRASES_LEAD_TEXT,
            pause_ms_after=KEY_PHRASE_LEAD_PAUSE_MS,
        )
    ]
    segments.extend(
        Segment(
            speaker=NARRATOR_ID,
            text=format_key_phrase(kp),
            pause_ms_after=KEY_PHRASE_PAUSE_MS,
        )
        for kp in key_phrases
    )
    # Key phrases is the final section of the file, so its last line
    # carries no trailing pause at all.
    return finalize_section("key_phrases", segments, last_pause_ms=0)


def build_sections(
    passage_lines: List[PassageLine],
    questions: List[Question],
    key_phrases: List[KeyPhrase],
) -> List[Section]:
    """Assemble the sections that feed the audio pipeline.

    Section order:
        preview_questions, passage, questions_with_choices, answers, key_phrases.
    The section-level long/short pauses are inserted by the TTS merge step.
    """
    return [
        _build_preview_questions_section(questions),
        _build_passage_section(passage_lines),
        _build_questions_with_choices_section(questions),
        _build_answers_section(questions),
        _build_key_phrases_section(key_phrases),
    ]


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def generate_dialogue(
    client: OpenAI,
    model: str,
    topic: str,
    num_speakers: int,
    num_turns: int,
    *,
    part: int = 3,
    difficulty: str = DEFAULT_DIFFICULTY,
) -> Dialogue:
    """Call the LLM with a structured-output schema and assemble the transcript.

    Raises:
        RuntimeError: Structured LLM response was empty.
    """
    num_speakers = normalize_speaker_count(part, num_speakers)
    prompt = build_prompt(part, difficulty, topic, num_speakers, num_turns)

    completion = client.chat.completions.parse(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        response_format=TranscriptResponse,
    )
    parsed: Optional[TranscriptResponse] = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Structured LLM response was empty.")

    speakers = assign_voices(num_speakers)
    speakers[NARRATOR_ID] = SpeakerConfig(**NARRATOR_VOICE_CONFIG)

    sections = build_sections(parsed.passage, parsed.questions, parsed.key_phrases)

    return Dialogue(
        title=parsed.title,
        slug=parsed.slug or _slugify(parsed.title),
        part=part,
        difficulty=difficulty,
        speakers=speakers,
        questions=parsed.questions,
        key_phrases=parsed.key_phrases,
        sections=sections,
    )


def _slugify(text: str) -> str:
    return "".join(
        c if c.isalnum() else "_" for c in text.strip().lower()
    ).strip("_") or "dialogue"


def save_dialogue(data: Dialogue, outdir: Path) -> Path:
    """Write a Dialogue to a JSON file, avoiding overwrite."""
    outdir.mkdir(parents=True, exist_ok=True)
    slug = data.slug or "dialogue"
    out_path = outdir / f"{slug}.json"

    counter = 1
    while out_path.exists():
        out_path = outdir / f"{slug}_{counter}.json"
        counter += 1

    out_path.write_text(
        data.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate TOEIC Part 3 / Part 4 transcript JSON."
    )
    parser.add_argument("--part", type=int, required=True, choices=list(VALID_PARTS))
    parser.add_argument("--difficulty", default=DEFAULT_DIFFICULTY, choices=list(VALID_DIFFICULTIES))
    parser.add_argument("--topic", required=True, help="Topic (e.g. 'hotel check-in')")
    parser.add_argument("--speakers", type=int, default=None, choices=[2, 3], help="Part 3 only: 2 or 3 speakers")
    parser.add_argument("--turns", type=int, default=None, help="Passage length (turns or sentences)")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_TRANSCRIPT_DIR)
    parser.add_argument("--model", default=DEFAULT_CHAT_MODEL)
    return parser


def main() -> int:
    parser = build_argparser()
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY or API_KEY is not set.", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key)

    num_speakers = normalize_speaker_count(args.part, args.speakers)
    num_turns = args.turns if args.turns is not None else default_turns_for_part(args.part)

    print(
        f"Generating Part {args.part} ({args.difficulty}): topic='{args.topic}', "
        f"speakers={num_speakers}, turns={num_turns} ..."
    )
    data = generate_dialogue(
        client,
        args.model,
        args.topic,
        num_speakers,
        num_turns,
        part=args.part,
        difficulty=args.difficulty,
    )

    out_path = save_dialogue(data, args.outdir)
    print(f"Saved: {out_path}")
    print(f"Title: {data.title}")
    print(f"Sections: {[s.type for s in data.sections]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
