#!/usr/bin/env python3
"""
TOEIC TTS Pipeline — transcript generation + audio synthesis for Part 3/4.

Usage:
    uv run python main.py --part 3 --topic "office relocation"
    uv run python main.py --part 4 --difficulty advanced --topic "quarterly earnings report"
    uv run python main.py --config examples/part3_sample_config.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI

from generator.config import (
    DEFAULT_AUDIO_DIR,
    DEFAULT_CHAT_MODEL,
    DEFAULT_DIFFICULTY,
    DEFAULT_TRANSCRIPT_DIR,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_MP3_BITRATE as DEFAULT_MP3_BITRATE,
    DEFAULT_TTS_OUTPUT_FORMAT as DEFAULT_OUTPUT_FORMAT,
    DEFAULT_TTS_SPEED as DEFAULT_SPEED,
    VALID_DIFFICULTIES,
    VALID_PARTS,
)
from generator.rules import (
    default_turns_for_part,
    normalize_speaker_count_with_warning,
    validate_difficulty,
    validate_part,
)
from generator.transcript import generate_dialogue, save_dialogue
from generator.tts import run as run_tts

load_dotenv()


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate TOEIC Part 3/4 transcript and synthesize audio in one step.",
    )

    parser.add_argument("--config", type=Path, default=None, help="JSON config file (CLI flags override values)")

    # Transcript options
    parser.add_argument("--part", type=int, choices=list(VALID_PARTS), help="TOEIC part: 3 (dialogue) or 4 (narration)")
    parser.add_argument("--difficulty", choices=list(VALID_DIFFICULTIES), help=f"Difficulty level (default: {DEFAULT_DIFFICULTY})")
    parser.add_argument("--topic", help="Topic / scene (e.g. 'office relocation')")
    parser.add_argument("--speakers", type=int, choices=[1, 2, 3], help="Number of passage speakers (Part 3: 2-3, Part 4: 1)")
    parser.add_argument("--turns", type=int, help="Passage length (dialogue turns for Part 3, sentences for Part 4)")
    parser.add_argument("--chat-model", default=None, help=f"Chat model (default: {DEFAULT_CHAT_MODEL})")

    # TTS options
    parser.add_argument("--tts-model", default=None, help=f"TTS model (default: {DEFAULT_TTS_MODEL})")
    parser.add_argument("--speed", type=float, default=None, help=f"Speaking speed, 0.25-4.0 (default: {DEFAULT_SPEED})")
    parser.add_argument(
        "--output-format",
        default=None,
        choices=["wav", "mp3"],
        help=f"Final audio format (default: {DEFAULT_OUTPUT_FORMAT})",
    )
    parser.add_argument(
        "--mp3-bitrate",
        default=None,
        choices=["128k", "256k"],
        help=f"MP3 bitrate (default: {DEFAULT_MP3_BITRATE})",
    )

    # Output options
    parser.add_argument("--transcript-dir", type=Path, default=None, help="Transcript output directory (default: transcripts)")
    parser.add_argument("--audio-dir", type=Path, default=None, help="Audio output base directory (default: output)")

    return parser


@dataclass
class Settings:
    part: int
    topic: str
    difficulty: str
    num_speakers: int
    turns: int
    chat_model: str
    tts_model: str
    speed: float
    output_format: str
    mp3_bitrate: str
    transcript_dir: Path
    audio_dir: Path


def _load_config(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config file {path} must contain a JSON object at the top level.")
    return cfg


def _merge(cli_value: Any, cfg: Dict[str, Any], key: str, default: Any) -> Any:
    """CLI > config file > default."""
    if cli_value is not None:
        return cli_value
    if key in cfg and cfg[key] is not None:
        return cfg[key]
    return default


def _resolve_settings(args: argparse.Namespace) -> Settings:
    cfg = _load_config(args.config)

    part = _merge(args.part, cfg, "part", None)
    if part is None:
        raise SystemExit("ERROR: --part is required (either via CLI or config file).")
    try:
        part = validate_part(part)
    except ValueError:
        raise SystemExit(f"ERROR: part must be one of {VALID_PARTS}, got {part}")

    topic = _merge(args.topic, cfg, "topic", None)
    if not topic:
        raise SystemExit("ERROR: --topic is required (either via CLI or config file).")

    difficulty = _merge(args.difficulty, cfg, "difficulty", DEFAULT_DIFFICULTY)
    try:
        difficulty = validate_difficulty(difficulty)
    except ValueError:
        raise SystemExit(f"ERROR: difficulty must be one of {VALID_DIFFICULTIES}")

    raw_speakers = _merge(args.speakers, cfg, "speakers", None)
    try:
        num_speakers = normalize_speaker_count_with_warning(part, raw_speakers)
    except ValueError as e:
        raise SystemExit(f"ERROR: {e}")

    turns = _merge(args.turns, cfg, "turns", None)
    if turns is None:
        turns = default_turns_for_part(part)

    transcript_dir = _merge(args.transcript_dir, cfg, "transcript_dir", DEFAULT_TRANSCRIPT_DIR)
    audio_dir = _merge(args.audio_dir, cfg, "audio_dir", DEFAULT_AUDIO_DIR)

    return Settings(
        part=part,
        topic=topic,
        difficulty=difficulty,
        num_speakers=num_speakers,
        turns=int(turns),
        chat_model=_merge(args.chat_model, cfg, "chat_model", DEFAULT_CHAT_MODEL),
        tts_model=_merge(args.tts_model, cfg, "tts_model", DEFAULT_TTS_MODEL),
        speed=float(_merge(args.speed, cfg, "speed", DEFAULT_SPEED)),
        output_format=_merge(args.output_format, cfg, "output_format", DEFAULT_OUTPUT_FORMAT),
        mp3_bitrate=_merge(args.mp3_bitrate, cfg, "mp3_bitrate", DEFAULT_MP3_BITRATE),
        transcript_dir=Path(transcript_dir),
        audio_dir=Path(audio_dir),
    )


def main() -> int:
    parser = build_argparser()
    args = parser.parse_args()

    settings = _resolve_settings(args)

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY or API_KEY is not set.", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key)

    print("=== Step 1: Generating transcript ===")
    print(
        f"Part {settings.part} | Difficulty: {settings.difficulty} | "
        f"Topic: {settings.topic} | Speakers: {settings.num_speakers} | "
        f"Turns: {settings.turns}"
    )

    data = generate_dialogue(
        client,
        settings.chat_model,
        settings.topic,
        settings.num_speakers,
        settings.turns,
        part=settings.part,
        difficulty=settings.difficulty,
    )
    transcript_path = save_dialogue(data, settings.transcript_dir)

    print(f"Saved: {transcript_path}")
    print(f"Title: {data.title}")
    print(f"Sections: {[s.type for s in data.sections]}")
    print(f"Questions: {len(data.questions)}")

    slug = data.slug or "toeic_listening"
    audio_outdir = settings.audio_dir / slug

    print("\n=== Step 2: Generating audio ===")
    print(f"Output: {audio_outdir}/")

    run_tts(
        dialogue_json=transcript_path,
        outdir=audio_outdir,
        model=settings.tts_model,
        output_format=settings.output_format,
        mp3_bitrate=settings.mp3_bitrate,
        speed=settings.speed,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
