#!/usr/bin/env python3
"""
TOEIC Part 3-style dialogue transcript generator.

Uses OpenAI ChatCompletion to produce a 2-3 speaker conversation JSON
that can be fed into ``generator.tts`` for audio synthesis.

Usage (standalone):
    uv run python -m generator.transcript --topic "hotel check-in" --speakers 2
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_OUTDIR = Path("transcripts")
DEFAULT_TURNS = 6

# ---------------------------------------------------------------------------
# Voice / speaker presets
# ---------------------------------------------------------------------------

VOICE_POOL: Dict[str, List[Dict[str, Any]]] = {
    "female": [
        {"voice": "marin", "instructions": "Female speaker. Professional, calm, friendly, and easy to understand."},
        {"voice": "nova", "instructions": "Female speaker. Warm, expressive, and conversational."},
        {"voice": "shimmer", "instructions": "Female speaker. Clear, bright, and articulate."},
        {"voice": "coral", "instructions": "Female speaker. Relaxed, natural, and approachable."},
    ],
    "male": [
        {"voice": "cedar", "instructions": "Male speaker. Friendly, upbeat, and conversational with natural energy."},
        {"voice": "ash", "instructions": "Male speaker. Warm, engaging, and approachable with a light tone."},
        {"voice": "echo", "instructions": "Male speaker. Pleasant, clear, and naturally expressive."},
        {"voice": "onyx", "instructions": "Male speaker. Easygoing, personable, and naturally warm."},
    ],
}

SPEAKER_CONFIGS = {
    2: [
        {"id": "W", "gender": "female", "speed": 0.96},
        {"id": "M", "gender": "male", "speed": 0.98},
    ],
    3: [
        {"id": "W1", "gender": "female", "speed": 0.96},
        {"id": "M", "gender": "male", "speed": 0.98},
        {"id": "W2", "gender": "female", "speed": 0.97},
    ],
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def build_prompt(topic: str, num_speakers: int, num_turns: int) -> str:
    """Build a ChatCompletion prompt that asks the model to generate a TOEIC dialogue.

    Args:
        topic: Conversation topic (e.g. "hotel check-in").
        num_speakers: Number of speakers (2 or 3).
        num_turns: Total number of dialogue turns.

    Returns:
        A fully-formed prompt string ready to send to the Chat API.
    """
    speaker_configs = SPEAKER_CONFIGS[num_speakers]
    speaker_ids = [s["id"] for s in speaker_configs]
    speaker_list = ", ".join(speaker_ids)

    return f"""You are a TOEIC Part 3 listening test content creator.

Generate a realistic, natural English dialogue for TOEIC Part 3 listening practice.

Requirements:
- Topic: {topic}
- Speakers: {num_speakers} people ({speaker_list})
- Total turns: exactly {num_turns} lines of dialogue
- Each speaker must speak at least 2 times
- Every speaker must appear in the conversation
- Use natural, professional English appropriate for TOEIC test difficulty
- Each line should be 1-2 sentences, concise and clear
- The conversation should have a clear context (workplace, store, hotel, etc.)
- Include realistic details (names, times, places, numbers) where appropriate

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "title": "Short descriptive title",
  "slug": "snake_case_slug",
  "lines": [
    {{"speaker": "{speaker_ids[0]}", "text": "...", "pause_ms_after": 400-500}},
    {{"speaker": "{speaker_ids[1]}", "text": "...", "pause_ms_after": 400-500}}
  ]
}}

Rules for pause_ms_after:
- Normal turn transitions: 400-450ms
- After questions or topic changes: 450-500ms
- Quick replies: 350-400ms
- Last line: 300-350ms"""


def assign_voices(num_speakers: int) -> Dict[str, Dict[str, Any]]:
    """Randomly assign TTS voices to each speaker from the pool.

    Each speaker receives a unique voice matching their gender.
    The result dict is keyed by speaker ID (e.g. "W", "M")
    and contains ``voice``, ``speed``, and ``instructions``.

    Args:
        num_speakers: Number of speakers (2 or 3).

    Returns:
        Speaker configuration dict ready to embed in the dialogue JSON.
    """
    configs = SPEAKER_CONFIGS[num_speakers]
    used_female: List[int] = []
    used_male: List[int] = []
    speakers: Dict[str, Dict[str, Any]] = {}

    for cfg in configs:
        pool = VOICE_POOL[cfg["gender"]]
        used = used_female if cfg["gender"] == "female" else used_male
        available = [i for i in range(len(pool)) if i not in used]
        idx = random.choice(available)
        used.append(idx)

        voice_cfg = pool[idx]
        speakers[cfg["id"]] = {
            "voice": voice_cfg["voice"],
            "speed": cfg["speed"],
            "instructions": voice_cfg["instructions"],
        }

    return speakers


def generate_dialogue(
    client: OpenAI, model: str, topic: str, num_speakers: int, num_turns: int,
) -> Dict[str, Any]:
    """Call the ChatCompletion API to generate a dialogue and attach voice configs.

    Args:
        client: An authenticated OpenAI client instance.
        model: Chat model name (e.g. "gpt-4o-mini").
        topic: Conversation topic.
        num_speakers: Number of speakers (2 or 3).
        num_turns: Total number of dialogue turns.

    Returns:
        Complete dialogue dict with ``title``, ``slug``, ``speakers``, and ``lines``.

    Raises:
        RuntimeError: If the API returns an empty response.
        ValueError: If the response is missing required fields.
    """
    prompt = build_prompt(topic, num_speakers, num_turns)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Empty response from API.")

    data = json.loads(content)

    if "title" not in data or "lines" not in data:
        raise ValueError("Response missing 'title' or 'lines'.")

    speakers = assign_voices(num_speakers)
    data["speakers"] = speakers

    return data


def save_dialogue(data: Dict[str, Any], outdir: Path) -> Path:
    """Write dialogue data to a JSON file under *outdir*.

    The filename is derived from the ``slug`` field.  If a file with
    the same name already exists, a numeric suffix is appended to
    avoid overwriting.

    Args:
        data: Dialogue dict (as returned by :func:`generate_dialogue`).
        outdir: Directory to save the JSON file in.

    Returns:
        The path to the written JSON file.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    slug = data.get("slug", "dialogue")
    out_path = outdir / f"{slug}.json"

    counter = 1
    while out_path.exists():
        out_path = outdir / f"{slug}_{counter}.json"
        counter += 1

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    """Create the argument parser for standalone CLI usage."""
    parser = argparse.ArgumentParser(
        description="Generate TOEIC Part 3-style dialogue transcript JSON."
    )
    parser.add_argument("--topic", required=True, help="Conversation topic (e.g. 'hotel check-in')")
    parser.add_argument("--speakers", type=int, default=2, choices=[2, 3], help="Number of speakers (default: 2)")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS, help=f"Number of dialogue turns (default: {DEFAULT_TURNS})")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help=f"Output directory (default: {DEFAULT_OUTDIR})")
    parser.add_argument("--model", default=DEFAULT_CHAT_MODEL, help=f"Chat model (default: {DEFAULT_CHAT_MODEL})")
    return parser


def main() -> int:
    """CLI entry point: parse args, generate dialogue, save to disk."""
    parser = build_argparser()
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY or API_KEY is not set.", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key)

    print(f"Generating dialogue: topic='{args.topic}', speakers={args.speakers}, turns={args.turns} ...")
    data = generate_dialogue(client, args.model, args.topic, args.speakers, args.turns)

    out_path = save_dialogue(data, args.outdir)

    print(f"Saved: {out_path}")
    print(f"Title: {data['title']}")
    print(f"Lines: {len(data['lines'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
