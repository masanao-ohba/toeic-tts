#!/usr/bin/env python3
"""
TOEIC Part 3 / Part 4 audio synthesizer.

Reads a transcript JSON produced by ``generator.transcript`` (new
``sections[]`` schema), synthesizes each line as a lossless WAV,
concatenates all sections with fixed inter-section pauses (short
between most sections, long before the answers), and optionally
converts the final result to MP3.

Pipeline:
    API → per-line WAV → concat by section → WAV → (optional) MP3
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import wave
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

from generator.config import (
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_MP3_BITRATE,
    DEFAULT_TTS_OUTPUT_FORMAT,
    DEFAULT_TTS_SPEED,
    LONG_PAUSE_MS,
    PASSAGE_CAST_PROMPT,
    SECTION_TRAILING_PAUSE_MS,
    SHORT_PAUSE_MS,
)
from generator.types import Dialogue, DialogueLine, Section, SpeakerConfig

load_dotenv()

# Backwards-compatible aliases exposed to callers importing from tts.py.
DEFAULT_MODEL = DEFAULT_TTS_MODEL
DEFAULT_OUTPUT_FORMAT = DEFAULT_TTS_OUTPUT_FORMAT
DEFAULT_MP3_BITRATE = DEFAULT_TTS_MP3_BITRATE
DEFAULT_SPEED = DEFAULT_TTS_SPEED

SECTION_SHORT_PAUSE_MS = SHORT_PAUSE_MS
SECTION_LONG_PAUSE_MS = LONG_PAUSE_MS


# ---------------------------------------------------------------------------
# Dialogue loading / validation
# ---------------------------------------------------------------------------


def load_dialogue(path: Path) -> Dialogue:
    """Load and validate a transcript JSON file via the Pydantic model."""
    return Dialogue.model_validate_json(path.read_text(encoding="utf-8"))


def ensure_outdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# TTS synthesis
# ---------------------------------------------------------------------------


def build_instructions(
    speaker_cfg: SpeakerConfig,
    section_type: str,
) -> str:
    base = speaker_cfg.instructions

    if section_type in (
        "preview_questions",
        "questions_and_answers",
    ):
        return (
            f"{base} You are a TOEIC test narrator. Read this English line "
            f"clearly and precisely for a standardized listening test. Neutral "
            f"tone, steady pace, no extra words or emotion."
        )

    if section_type == "key_phrases":
        return (
            f"{base} You are a TOEIC key-phrase narrator. Each line contains an "
            f"English phrase followed by its Japanese translation. Read the "
            f"English portion first in clear English, then read the Japanese "
            f"portion in natural, native-sounding Japanese. Neutral tone, steady "
            f"pace, no extra words or emotion."
        )

    return f"{base} {PASSAGE_CAST_PROMPT}"


def synthesize_one_line(
    client: OpenAI,
    *,
    model: str,
    speaker_name: str,
    speaker_cfg: SpeakerConfig,
    line: DialogueLine,
    out_path: Path,
    default_speed: float,
    section_type: str = "passage",
) -> None:
    """Synthesize a single line and save it as a WAV file."""
    voice = speaker_cfg.voice
    if not voice:
        raise ValueError(f"Speaker '{speaker_name}' has no voice configured.")

    speed = float(speaker_cfg.speed or default_speed)
    instructions = build_instructions(speaker_cfg, section_type)

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=line.text,
        instructions=instructions,
        response_format="wav",
        speed=speed,
    ) as response:
        response.stream_to_file(out_path)


# ---------------------------------------------------------------------------
# WAV manipulation
# ---------------------------------------------------------------------------


def read_wav(path: Path) -> tuple[wave._wave_params, bytes]:
    with wave.open(str(path), "rb") as wf:
        params = wf.getparams()
        frames = wf.readframes(wf.getnframes())
    return params, frames


def silence_bytes(params: wave._wave_params, duration_ms: int) -> bytes:
    num_frames = int(params.framerate * duration_ms / 1000)
    bytes_per_frame = params.nchannels * params.sampwidth
    return b"\x00" * (num_frames * bytes_per_frame)


def concat_wavs(
    wav_paths: List[Path],
    pause_ms_after: List[int],
    out_path: Path,
) -> None:
    """Concatenate WAV files, inserting per-line silence between them.

    ``pause_ms_after[i]`` is inserted after ``wav_paths[i]``. The pause
    after the final element (if present) is written; pass 0 to suppress it.
    """
    if not wav_paths:
        raise ValueError("No wav files to concatenate.")
    if len(pause_ms_after) != len(wav_paths):
        raise ValueError(
            f"pause_ms_after length ({len(pause_ms_after)}) must match "
            f"wav_paths length ({len(wav_paths)})"
        )

    base_params, first_frames = read_wav(wav_paths[0])
    merged = bytearray(first_frames)
    if pause_ms_after[0]:
        merged.extend(silence_bytes(base_params, pause_ms_after[0]))

    for idx, wav_path in enumerate(wav_paths[1:], start=1):
        params, frames = read_wav(wav_path)
        a = (base_params.nchannels, base_params.sampwidth, base_params.framerate, base_params.comptype)
        b = (params.nchannels, params.sampwidth, params.framerate, params.comptype)
        if a != b:
            raise ValueError(
                f"WAV format mismatch while merging: {wav_path.name} {b} != {a}"
            )
        merged.extend(frames)
        if pause_ms_after[idx]:
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
    audio = AudioSegment.from_wav(str(wav_path))
    audio.export(str(mp3_path), format="mp3", bitrate=bitrate)


# ---------------------------------------------------------------------------
# Transcript output
# ---------------------------------------------------------------------------


def write_transcript(data: Dialogue, out_path: Path) -> None:
    """Write a human-readable text version of the transcript."""
    title = data.title
    part = data.part
    difficulty = data.difficulty

    with out_path.open("w", encoding="utf-8") as f:
        header = f"{title}  [Part {part} / {difficulty}]"
        f.write(header + "\n")
        f.write("=" * len(header) + "\n\n")

        idx = 1
        for section in data.sections:
            f.write(f"-- {section.type} --\n")
            for line in section.lines:
                f.write(f"{idx:02d}. [{line.speaker}] {line.text}\n")
                f.write(f"    pause_ms_after={line.pause_ms_after}\n")
                idx += 1
            f.write("\n")

        if data.questions:
            f.write("== Answer Key ==\n")
            for q in data.questions:
                f.write(f"Q{q.id}: {q.answer}\n")
            f.write("\n")

        if data.key_phrases:
            f.write("== Key Phrases ==\n")
            for i, kp in enumerate(data.key_phrases, start=1):
                f.write(f"{i:02d}. {kp.en}\n")
                f.write(f"    -> {kp.ja}\n")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def _trailing_pause_for(section_type: str) -> int:
    """Return the section-boundary pause (ms) inserted after the final line
    of the given section. Section boundaries always use the fixed spec
    pauses so audio layout is stable regardless of per-line hints."""
    return SECTION_TRAILING_PAUSE_MS.get(section_type, SHORT_PAUSE_MS)


def _iter_section_lines(
    sections: List[Section],
) -> List[Tuple[int, str, DialogueLine, bool]]:
    """Flatten sections into (global_index, section_type, line, is_last_in_section).

    Index starts at 1 for file naming.
    """
    out: List[Tuple[int, str, DialogueLine, bool]] = []
    idx = 1
    for section in sections:
        stype = section.type
        lines = section.lines
        for i, line in enumerate(lines):
            is_last = i == len(lines) - 1
            out.append((idx, stype, line, is_last))
            idx += 1
    return out


def run(
    dialogue_json: Path,
    outdir: Path = Path("output"),
    model: str = DEFAULT_MODEL,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    mp3_bitrate: str = DEFAULT_MP3_BITRATE,
    speed: float = DEFAULT_SPEED,
    work_dir: Path | None = None,
) -> Path:
    """Run the full audio pipeline against a sections[] transcript.

    Intermediate WAV files are created in a temporary directory and
    cleaned up automatically. Only the final output (MP3 or WAV) is
    written to ``outdir``. If ``work_dir`` is given, the human-readable
    transcript text is saved there.
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY or API_KEY is not set.")

    data = load_dialogue(dialogue_json)
    ensure_outdir(outdir)

    client = OpenAI(api_key=api_key)

    sections = data.sections
    total_lines = sum(len(s.lines) for s in sections)

    final_name = data.slug or "toeic_listening"

    with tempfile.TemporaryDirectory(prefix="toeic_tts_") as tmpdir:
        workdir = Path(tmpdir)
        per_line_paths: List[Path] = []
        pauses: List[int] = []

        flat = _iter_section_lines(sections)
        for (idx, stype, line, is_last_in_section) in flat:
            speaker_name = line.speaker
            speaker_cfg = data.speakers[speaker_name]
            line_path = workdir / f"{idx:02d}_{stype}_{speaker_name}.wav"

            print(f"[{idx}/{total_lines}] ({stype}) {line_path.name}")
            synthesize_one_line(
                client,
                model=model,
                speaker_name=speaker_name,
                speaker_cfg=speaker_cfg,
                line=line,
                out_path=line_path,
                default_speed=speed,
                section_type=stype,
            )

            per_line_paths.append(line_path)

            if is_last_in_section:
                pauses.append(_trailing_pause_for(stype))
            else:
                pauses.append(int(line.pause_ms_after))

        txt_dir = work_dir if work_dir is not None else workdir
        txt_dir.mkdir(parents=True, exist_ok=True)
        write_transcript(data, txt_dir / "transcript.txt")

        full_wav = workdir / f"{final_name}_full.wav"
        concat_wavs(per_line_paths, pauses, full_wav)

        if output_format == "mp3":
            full_mp3 = outdir / f"{final_name}_full.mp3"
            print(f"Converting to MP3 ({mp3_bitrate}) ...")
            convert_wav_to_mp3(full_wav, full_mp3, bitrate=mp3_bitrate)
            print(f"\nDone: {full_mp3}")
            return full_mp3

        import shutil
        final_out = outdir / f"{final_name}_full.wav"
        shutil.move(str(full_wav), str(final_out))
        print(f"\nDone: {final_out}")
        return final_out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synthesize TOEIC Part 3 / Part 4 audio from a sections[] transcript."
    )
    parser.add_argument("dialogue_json", type=Path)
    parser.add_argument("--outdir", type=Path, default=Path("output"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT, choices=["wav", "mp3"])
    parser.add_argument("--mp3-bitrate", default=DEFAULT_MP3_BITRATE, choices=["128k", "256k"])
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED)
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
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
