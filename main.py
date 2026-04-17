#!/usr/bin/env python3
"""TOEIC TTS pipeline — transcript generation + audio synthesis for Part 3/4.

Usage:
    uv run python main.py --part 3 --topic "office relocation"
    uv run python main.py --part 4 --difficulty advanced --topic "quarterly earnings report"
    uv run python main.py --config examples/part3_sample_config.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI

from generator.config import DEFAULT_AUDIO_DIR, DEFAULT_WORK_DIR
from generator.difficulty import DIFFICULTY_PROFILES
from generator.transcript import generate_dialogue, save_dialogue
from generator.tts import run as run_tts

load_dotenv()

DIFFICULTY_CHOICES = list(DIFFICULTY_PROFILES.keys())
PART_CHOICES = [3, 4]
DEFAULT_DIFFICULTY = "intermediate"
DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_OUTPUT_FORMAT = "mp3"
DEFAULT_MP3_BITRATE = "128k"
DEFAULT_TURNS = {3: 8, 4: 6}


def _load_config(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_parser(defaults: Dict[str, Any]) -> argparse.ArgumentParser:
    """Build the argparse parser. ``defaults`` supplies values read from a
    config file — these become the parser's defaults, so CLI flags still
    override them naturally."""
    parser = argparse.ArgumentParser(
        description="Generate TOEIC Part 3/4 transcript and synthesize audio.",
    )

    parser.add_argument("--config", type=Path, default=None, help="JSON config file (CLI flags override its values)")

    parser.add_argument(
        "--part",
        type=int,
        choices=PART_CHOICES,
        default=defaults.get("part"),
        required="part" not in defaults,
        help="TOEIC part: 3 (dialogue) or 4 (narration)",
    )
    parser.add_argument(
        "--difficulty",
        choices=DIFFICULTY_CHOICES,
        default=defaults.get("difficulty", DEFAULT_DIFFICULTY),
        help=(
            f"Item difficulty (default: {DEFAULT_DIFFICULTY}). "
            "beginner=A2/400-550, intermediate=B1/550-780, "
            "advanced=B2/780-860, expert=C1/860+."
        ),
    )
    parser.add_argument(
        "--topic",
        default=defaults.get("topic"),
        required="topic" not in defaults,
        help="Topic / scene (e.g. 'office relocation')",
    )
    parser.add_argument(
        "--speakers",
        type=int,
        choices=[1, 2, 3],
        default=defaults.get("speakers"),
        help="Number of passage speakers (Part 3: 2 or 3; Part 4: 1)",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=defaults.get("turns"),
        help="Passage length (dialogue turns for Part 3, sentences for Part 4)",
    )

    parser.add_argument("--chat-model", default=defaults.get("chat_model", DEFAULT_CHAT_MODEL))
    parser.add_argument("--tts-model", default=defaults.get("tts_model", DEFAULT_TTS_MODEL))
    parser.add_argument("--speed", type=float, default=defaults.get("speed"),
                        help="Override the per-speaker TTS speed (optional)")
    parser.add_argument(
        "--output-format",
        choices=["wav", "mp3"],
        default=defaults.get("output_format", DEFAULT_OUTPUT_FORMAT),
    )
    parser.add_argument(
        "--mp3-bitrate",
        choices=["128k", "256k"],
        default=defaults.get("mp3_bitrate", DEFAULT_MP3_BITRATE),
    )

    parser.add_argument("--audio-dir", type=Path, default=Path(defaults.get("audio_dir", DEFAULT_AUDIO_DIR)))
    parser.add_argument("--work-dir", type=Path, default=Path(defaults.get("work_dir", DEFAULT_WORK_DIR)))

    return parser


def _resolve_speakers(part: int, requested: Optional[int]) -> int:
    if part == 4:
        if requested not in (None, 1):
            raise SystemExit(f"ERROR: Part 4 requires --speakers 1 (got {requested}).")
        return 1
    if requested is None:
        return 2
    if requested in (2, 3):
        return requested
    raise SystemExit(f"ERROR: Part 3 requires --speakers 2 or 3 (got {requested}).")


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path, default=None)
    pre_args, _ = pre.parse_known_args()

    cfg_defaults = _load_config(pre_args.config)
    args = _build_parser(cfg_defaults).parse_args()

    num_speakers = _resolve_speakers(args.part, args.speakers)
    num_turns = args.turns if args.turns is not None else DEFAULT_TURNS[args.part]

    client = OpenAI()

    print("=== Step 1: Generating transcript ===")
    print(
        f"Part {args.part} | Difficulty: {args.difficulty} | "
        f"Topic: {args.topic} | Speakers: {num_speakers} | Turns: {num_turns}"
    )

    data = generate_dialogue(
        client,
        model=args.chat_model,
        topic=args.topic,
        part=args.part,
        difficulty=args.difficulty,
        num_speakers=num_speakers,
        num_turns=num_turns,
    )

    args.work_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = save_dialogue(data, args.work_dir)

    print(f"Transcript (work): {transcript_path}")
    print(f"Title: {data.title}")
    print(f"Sections: {[s.type for s in data.sections]}")
    print(f"Questions: {len(data.questions)}")

    if args.speed is not None:
        for cfg in data.speakers.values():
            cfg.speed = args.speed

    print("\n=== Step 2: Generating audio ===")
    print(f"Output: {args.audio_dir}/")

    run_tts(
        client,
        transcript_path,
        outdir=args.audio_dir,
        model=args.tts_model,
        output_format=args.output_format,
        mp3_bitrate=args.mp3_bitrate,
        work_dir=args.work_dir,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
