#!/usr/bin/env python3
"""
TOEIC TTS Pipeline — transcript generation + audio synthesis in one shot.

Usage:
    uv run python main.py --topic "hotel check-in"
    uv run python main.py --topic "project deadline" --speakers 3 --turns 8
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from generator.transcript import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_TURNS,
    generate_dialogue,
    save_dialogue,
)
from generator.tts import (
    DEFAULT_MODEL as DEFAULT_TTS_MODEL,
    DEFAULT_MP3_BITRATE,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_SPEED,
    run as run_tts,
)

load_dotenv()


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate TOEIC dialogue transcript and synthesize audio in one step.",
    )

    # Transcript options
    parser.add_argument("--topic", required=True, help="Conversation topic (e.g. 'hotel check-in')")
    parser.add_argument("--speakers", type=int, default=2, choices=[2, 3], help="Number of speakers (default: 2)")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS, help=f"Number of dialogue turns (default: {DEFAULT_TURNS})")
    parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL, help=f"Chat model for transcript generation (default: {DEFAULT_CHAT_MODEL})")

    # TTS options
    parser.add_argument("--tts-model", default=DEFAULT_TTS_MODEL, help=f"TTS model (default: {DEFAULT_TTS_MODEL})")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED, help=f"Speaking speed, 0.25-4.0 (default: {DEFAULT_SPEED})")
    parser.add_argument(
        "--output-format",
        default=DEFAULT_OUTPUT_FORMAT,
        choices=["wav", "mp3"],
        help=f"Final audio format (default: {DEFAULT_OUTPUT_FORMAT})",
    )
    parser.add_argument(
        "--mp3-bitrate",
        default=DEFAULT_MP3_BITRATE,
        choices=["128k", "256k"],
        help=f"MP3 bitrate (default: {DEFAULT_MP3_BITRATE})",
    )

    # Output options
    parser.add_argument("--transcript-dir", type=Path, default=Path("transcripts"), help="Transcript output directory (default: transcripts)")
    parser.add_argument("--audio-dir", type=Path, default=Path("output"), help="Audio output base directory (default: output)")

    return parser


def main() -> int:
    parser = build_argparser()
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY or API_KEY is not set.", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key)

    # Step 1: Generate transcript
    print(f"=== Step 1: Generating transcript ===")
    print(f"Topic: {args.topic} | Speakers: {args.speakers} | Turns: {args.turns}")

    data = generate_dialogue(client, args.chat_model, args.topic, args.speakers, args.turns)
    transcript_path = save_dialogue(data, args.transcript_dir)

    print(f"Saved: {transcript_path}")
    print(f"Title: {data['title']}")
    print(f"Lines: {len(data['lines'])}")

    # Step 2: Generate audio
    slug = data.get("slug", "dialogue")
    audio_outdir = args.audio_dir / slug

    print(f"\n=== Step 2: Generating audio ===")
    print(f"Output: {audio_outdir}/")

    run_tts(
        dialogue_json=transcript_path,
        outdir=audio_outdir,
        model=args.tts_model,
        output_format=args.output_format,
        mp3_bitrate=args.mp3_bitrate,
        speed=args.speed,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
