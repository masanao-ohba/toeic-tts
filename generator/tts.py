#!/usr/bin/env python3
"""
TOEIC Part 3-style dialogue audio generator using OpenAI TTS.

Reads a dialogue JSON, synthesizes each utterance with a different voice,
inserts pauses between turns, merges into one WAV, then converts to MP3.

Usage (standalone):
    uv run python -m generator.tts transcripts/sample_dialogue.json --outdir output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import wave
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

load_dotenv()

DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_OUTPUT_FORMAT = "mp3"
DEFAULT_MP3_BITRATE = "128k"
DEFAULT_SPEED = 0.97


def load_dialogue(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "speakers" not in data or "lines" not in data:
        raise ValueError("JSON must contain 'speakers' and 'lines'.")

    if not isinstance(data["speakers"], dict) or not isinstance(data["lines"], list):
        raise ValueError("'speakers' must be an object and 'lines' must be a list.")

    for i, line in enumerate(data["lines"], start=1):
        if "speaker" not in line or "text" not in line:
            raise ValueError(f"Line {i} must contain 'speaker' and 'text'.")
        if line["speaker"] not in data["speakers"]:
            raise ValueError(f"Line {i} refers to unknown speaker: {line['speaker']}")

    return data


def ensure_outdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def synthesize_one_line(
    client: OpenAI,
    *,
    model: str,
    speaker_name: str,
    speaker_cfg: Dict[str, Any],
    line: Dict[str, Any],
    out_path: Path,
    default_speed: float,
) -> None:
    voice = line.get("voice") or speaker_cfg.get("voice")
    if not voice:
        raise ValueError(f"Speaker '{speaker_name}' has no voice configured.")

    instructions = line.get("instructions") or speaker_cfg.get("instructions", "")
    speed = float(line.get("speed", speaker_cfg.get("speed", default_speed)))

    style_suffix = (
        " Speak naturally and clearly for English listening practice. "
        "Use clean articulation, moderate pacing, and short natural pauses. "
        "Do not add extra words, labels, or sound effects."
    )

    final_instructions = (instructions + " " + style_suffix).strip()

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=line["text"],
        instructions=final_instructions,
        response_format="wav",
        speed=speed,
    ) as response:
        response.stream_to_file(out_path)


def read_wav(path: Path) -> tuple[wave._wave_params, bytes]:
    with wave.open(str(path), "rb") as wf:
        params = wf.getparams()
        frames = wf.readframes(wf.getnframes())
    return params, frames


def silence_bytes(params: wave._wave_params, duration_ms: int) -> bytes:
    num_frames = int(params.framerate * duration_ms / 1000)
    bytes_per_frame = params.nchannels * params.sampwidth
    return b"\x00" * (num_frames * bytes_per_frame)


def concat_wavs(wav_paths: List[Path], pause_ms_after: List[int], out_path: Path) -> None:
    if not wav_paths:
        raise ValueError("No wav files to concatenate.")

    base_params, first_frames = read_wav(wav_paths[0])

    merged = bytearray(first_frames)
    if pause_ms_after:
        merged.extend(silence_bytes(base_params, pause_ms_after[0]))

    for idx, wav_path in enumerate(wav_paths[1:], start=1):
        params, frames = read_wav(wav_path)

        comparable_a = (base_params.nchannels, base_params.sampwidth, base_params.framerate, base_params.comptype)
        comparable_b = (params.nchannels, params.sampwidth, params.framerate, params.comptype)
        if comparable_a != comparable_b:
            raise ValueError(
                f"WAV format mismatch while merging: {wav_path.name} "
                f"{comparable_b} != {comparable_a}"
            )

        merged.extend(frames)
        if idx < len(pause_ms_after):
            merged.extend(silence_bytes(base_params, pause_ms_after[idx]))

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(base_params.nchannels)
        wf.setsampwidth(base_params.sampwidth)
        wf.setframerate(base_params.framerate)
        wf.setcomptype(base_params.comptype, base_params.compname)
        wf.writeframes(bytes(merged))


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path, bitrate: str = DEFAULT_MP3_BITRATE) -> None:
    audio = AudioSegment.from_wav(str(wav_path))
    audio.export(str(mp3_path), format="mp3", bitrate=bitrate)


def write_transcript(data: Dict[str, Any], out_path: Path) -> None:
    title = data.get("title", "Untitled Dialogue")
    lines = data["lines"]

    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"{title}\n")
        f.write("=" * len(title) + "\n\n")
        for i, line in enumerate(lines, start=1):
            pause_ms = line.get("pause_ms_after", 400)
            f.write(f"{i:02d}. [{line['speaker']}] {line['text']}\n")
            f.write(f"    pause_ms_after={pause_ms}\n")


def run(
    dialogue_json: Path,
    outdir: Path = Path("output"),
    model: str = DEFAULT_MODEL,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    mp3_bitrate: str = DEFAULT_MP3_BITRATE,
    speed: float = DEFAULT_SPEED,
) -> Path:
    """Generate audio from a dialogue JSON file. Returns the final output path."""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY or API_KEY is not set.")

    data = load_dialogue(dialogue_json)
    ensure_outdir(outdir)

    client = OpenAI(api_key=api_key)

    # Step 1: Synthesize each line as WAV (lossless)
    per_line_paths: List[Path] = []
    pauses: List[int] = []

    for i, line in enumerate(data["lines"], start=1):
        speaker_name = line["speaker"]
        speaker_cfg = data["speakers"][speaker_name]
        line_path = outdir / f"{i:02d}_{speaker_name}.wav"

        print(f"[{i}/{len(data['lines'])}] Synthesizing {line_path.name} ...")
        synthesize_one_line(
            client,
            model=model,
            speaker_name=speaker_name,
            speaker_cfg=speaker_cfg,
            line=line,
            out_path=line_path,
            default_speed=speed,
        )

        per_line_paths.append(line_path)
        pauses.append(int(line.get("pause_ms_after", 400)))

    write_transcript(data, outdir / "transcript.txt")

    # Step 2: Concat WAVs into one full WAV
    final_name = data.get("slug", "toeic_part3_dialogue")
    full_wav = outdir / f"{final_name}_full.wav"
    concat_wavs(per_line_paths, pauses, full_wav)

    # Step 3: Convert to final format
    if output_format == "mp3":
        full_mp3 = outdir / f"{final_name}_full.mp3"
        print(f"Converting to MP3 ({mp3_bitrate}) ...")
        convert_wav_to_mp3(full_wav, full_mp3, bitrate=mp3_bitrate)
        full_wav.unlink()
        for p in per_line_paths:
            p.unlink()
        print(f"\nDone: {full_mp3}")
        return full_mp3

    # WAV: keep as-is
    print(f"\nDone: {full_wav}")
    return full_wav


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate TOEIC Part 3-style multi-speaker dialogue audio."
    )
    parser.add_argument("dialogue_json", type=Path, help="Path to dialogue JSON")
    parser.add_argument("--outdir", type=Path, default=Path("output"), help="Output directory")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="TTS model name")
    parser.add_argument(
        "--output-format",
        default=DEFAULT_OUTPUT_FORMAT,
        choices=["wav", "mp3"],
        help="Final output format (default: mp3)",
    )
    parser.add_argument(
        "--mp3-bitrate",
        default=DEFAULT_MP3_BITRATE,
        choices=["128k", "256k"],
        help="MP3 bitrate (default: 128k)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=DEFAULT_SPEED,
        help="Default speaking speed (0.25 to 4.0)",
    )
    return parser


def main() -> int:
    parser = build_argparser()
    args = parser.parse_args()

    try:
        run(
            dialogue_json=args.dialogue_json,
            outdir=args.outdir,
            model=args.model,
            output_format=args.output_format,
            mp3_bitrate=args.mp3_bitrate,
            speed=args.speed,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
