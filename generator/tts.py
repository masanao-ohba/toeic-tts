#!/usr/bin/env python3
"""
TOEIC Part 3-style dialogue audio synthesizer.

Reads a dialogue JSON produced by ``generator.transcript``, synthesizes each
utterance as a lossless WAV via OpenAI TTS, concatenates them with natural
pauses, and optionally converts the final result to MP3.

Pipeline:
    API → per-line WAV → concat WAV → (optional) MP3 conversion

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


# ---------------------------------------------------------------------------
# Dialogue loading / validation
# ---------------------------------------------------------------------------


def load_dialogue(path: Path) -> Dict[str, Any]:
    """Load and validate a dialogue JSON file.

    The JSON must contain a ``speakers`` object and a ``lines`` array.
    Each line must reference a speaker defined in ``speakers``.

    Args:
        path: Path to the dialogue JSON file.

    Returns:
        Parsed dialogue dict.

    Raises:
        ValueError: If the JSON structure is invalid or references unknown speakers.
    """
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
    """Create the output directory (and parents) if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# TTS synthesis
# ---------------------------------------------------------------------------


def build_instructions(
    speaker_cfg: Dict[str, Any],
    line: Dict[str, Any],
    scene: str,
    prev_text: str,
) -> str:
    """Compose TTS instructions that produce a natural conversational tone.

    Combines the speaker's base persona, the scene context, and the
    previous utterance so that the TTS model delivers each line as
    part of a flowing dialogue rather than an isolated statement.

    Args:
        speaker_cfg: Speaker definition from the dialogue JSON.
        line: Current line dict (may override instructions).
        scene: Scene description (typically the dialogue ``title``).
        prev_text: The text of the immediately preceding line, or "" for the first line.

    Returns:
        A single instruction string for the TTS API.
    """
    base = line.get("instructions") or speaker_cfg.get("instructions", "")

    context_parts = [base]

    if scene:
        context_parts.append(f"Scene: {scene}")

    if prev_text:
        context_parts.append(
            f"You are responding to someone who just said: \"{prev_text}\" "
            "— react naturally to what they said."
        )

    context_parts.append(
        "You are in a live face-to-face conversation. "
        "Match the energy and flow of the dialogue. "
        "Speak naturally and clearly for English listening practice. "
        "Do not add extra words, labels, or sound effects."
    )

    return " ".join(context_parts)


def synthesize_one_line(
    client: OpenAI,
    *,
    model: str,
    speaker_name: str,
    speaker_cfg: Dict[str, Any],
    line: Dict[str, Any],
    out_path: Path,
    default_speed: float,
    scene: str = "",
    prev_text: str = "",
) -> None:
    """Synthesize a single dialogue line and save it as a WAV file.

    Always requests WAV from the API to keep per-line audio lossless.
    Format conversion (e.g. to MP3) is handled later at the merge stage.

    Args:
        client: Authenticated OpenAI client.
        model: TTS model name.
        speaker_name: Speaker ID (for error messages).
        speaker_cfg: Speaker configuration (voice, speed, instructions).
        line: Current dialogue line dict.
        out_path: Destination file path (.wav).
        default_speed: Fallback speaking speed.
        scene: Scene description passed to :func:`build_instructions`.
        prev_text: Previous line's text passed to :func:`build_instructions`.

    Raises:
        ValueError: If the speaker has no voice configured.
    """
    voice = line.get("voice") or speaker_cfg.get("voice")
    if not voice:
        raise ValueError(f"Speaker '{speaker_name}' has no voice configured.")

    speed = float(line.get("speed", speaker_cfg.get("speed", default_speed)))
    instructions = build_instructions(speaker_cfg, line, scene, prev_text)

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=line["text"],
        instructions=instructions,
        response_format="wav",
        speed=speed,
    ) as response:
        response.stream_to_file(out_path)


# ---------------------------------------------------------------------------
# WAV manipulation
# ---------------------------------------------------------------------------


def read_wav(path: Path) -> tuple[wave._wave_params, bytes]:
    """Read a WAV file and return its parameters and raw frame data."""
    with wave.open(str(path), "rb") as wf:
        params = wf.getparams()
        frames = wf.readframes(wf.getnframes())
    return params, frames


def silence_bytes(params: wave._wave_params, duration_ms: int) -> bytes:
    """Generate raw silence bytes matching the given WAV parameters.

    Args:
        params: WAV parameters (channels, sample width, frame rate).
        duration_ms: Duration of silence in milliseconds.

    Returns:
        A bytes object of zero-valued PCM samples.
    """
    num_frames = int(params.framerate * duration_ms / 1000)
    bytes_per_frame = params.nchannels * params.sampwidth
    return b"\x00" * (num_frames * bytes_per_frame)


def concat_wavs(wav_paths: List[Path], pause_ms_after: List[int], out_path: Path) -> None:
    """Concatenate multiple WAV files with pauses between them.

    All input WAVs must share the same audio format (channels,
    sample width, frame rate, compression type).

    Args:
        wav_paths: Ordered list of per-line WAV files.
        pause_ms_after: Silence duration (ms) to insert after each file.
        out_path: Destination path for the merged WAV.

    Raises:
        ValueError: If no paths are given or formats don't match.
    """
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


# ---------------------------------------------------------------------------
# Format conversion
# ---------------------------------------------------------------------------


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path, bitrate: str = DEFAULT_MP3_BITRATE) -> None:
    """Convert a WAV file to MP3 using pydub (requires ffmpeg).

    Args:
        wav_path: Source WAV file.
        mp3_path: Destination MP3 file.
        bitrate: Target bitrate (e.g. "128k", "256k").
    """
    audio = AudioSegment.from_wav(str(wav_path))
    audio.export(str(mp3_path), format="mp3", bitrate=bitrate)


# ---------------------------------------------------------------------------
# Transcript output
# ---------------------------------------------------------------------------


def write_transcript(data: Dict[str, Any], out_path: Path) -> None:
    """Write a human-readable text transcript alongside the audio files.

    Args:
        data: Dialogue dict containing ``title`` and ``lines``.
        out_path: Destination text file path.
    """
    title = data.get("title", "Untitled Dialogue")
    lines = data["lines"]

    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"{title}\n")
        f.write("=" * len(title) + "\n\n")
        for i, line in enumerate(lines, start=1):
            pause_ms = line.get("pause_ms_after", 400)
            f.write(f"{i:02d}. [{line['speaker']}] {line['text']}\n")
            f.write(f"    pause_ms_after={pause_ms}\n")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run(
    dialogue_json: Path,
    outdir: Path = Path("output"),
    model: str = DEFAULT_MODEL,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    mp3_bitrate: str = DEFAULT_MP3_BITRATE,
    speed: float = DEFAULT_SPEED,
) -> Path:
    """Run the full audio generation pipeline.

    1. Synthesize each dialogue line as a lossless WAV.
    2. Concatenate all WAVs with inter-turn pauses.
    3. Convert the merged WAV to the requested output format.
    4. Clean up intermediate WAV files (when output is MP3).

    Args:
        dialogue_json: Path to the dialogue JSON file.
        outdir: Directory for generated audio and transcript.
        model: OpenAI TTS model name.
        output_format: Final format — ``"mp3"`` or ``"wav"``.
        mp3_bitrate: Bitrate for MP3 encoding (e.g. ``"128k"``).
        speed: Default speaking speed (0.25–4.0).

    Returns:
        Path to the final merged audio file.

    Raises:
        RuntimeError: If no API key is configured.
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY or API_KEY is not set.")

    data = load_dialogue(dialogue_json)
    ensure_outdir(outdir)

    client = OpenAI(api_key=api_key)

    # Step 1: Synthesize each line as WAV (lossless)
    scene = data.get("title", "")
    per_line_paths: List[Path] = []
    pauses: List[int] = []
    prev_text = ""

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
            scene=scene,
            prev_text=prev_text,
        )

        prev_text = line["text"]
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    """Create the argument parser for standalone CLI usage."""
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
    """CLI entry point: parse args, run the full synthesis pipeline."""
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
