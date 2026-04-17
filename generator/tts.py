"""TOEIC Part 3 / Part 4 audio synthesis.

Reads a Dialogue JSON produced by ``generator.transcript``, synthesizes
each line as a WAV, concatenates everything with the section-boundary
pauses defined by the audio spec, and optionally exports as MP3.
"""

from __future__ import annotations

import shutil
import tempfile
import wave
from pathlib import Path
from typing import List, Tuple

from openai import OpenAI
from pydub import AudioSegment

from generator.config import (
    PASSAGE_CAST_PROMPT,
    SECTION_TRAILING_PAUSE_MS,
)
from generator.types import Dialogue, Line, Section, SpeakerConfig


# ---------------------------------------------------------------------------
# TTS synthesis
# ---------------------------------------------------------------------------


def _build_instructions(speaker_cfg: SpeakerConfig, section_type: str) -> str:
    base = speaker_cfg.instructions

    if section_type in ("preview_questions", "questions_and_answers"):
        return (
            f"{base} You are a TOEIC test narrator. Read this English line "
            f"clearly and precisely for a standardized listening test. Neutral "
            f"tone, steady pace, no extra words or emotion."
        )

    if section_type == "key_phrases":
        return (
            f"{base} You are a TOEIC key-phrase narrator. Each line contains an "
            f"English phrase, optionally followed by a Japanese translation. "
            f"Read the English portion in clear English. If — and only if — a "
            f"Japanese translation is present in the line, read it in natural, "
            f"native-sounding Japanese after the English. If no Japanese text "
            f"appears in the line, read only the English; do NOT invent, infer, "
            f"or append any Japanese translation. Neutral tone, steady pace, no "
            f"extra words or emotion."
        )

    return f"{base} {PASSAGE_CAST_PROMPT}"


def _synthesize_line(
    client: OpenAI,
    *,
    model: str,
    speaker_cfg: SpeakerConfig,
    line: Line,
    section_type: str,
    out_path: Path,
) -> None:
    instructions = _build_instructions(speaker_cfg, section_type)
    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=speaker_cfg.voice,
        input=line.text,
        instructions=instructions,
        response_format="wav",
        speed=speaker_cfg.speed,
    ) as response:
        response.stream_to_file(out_path)


# ---------------------------------------------------------------------------
# WAV manipulation
# ---------------------------------------------------------------------------


def _read_wav(path: Path) -> Tuple[wave._wave_params, bytes]:
    with wave.open(str(path), "rb") as wf:
        params = wf.getparams()
        frames = wf.readframes(wf.getnframes())
    return params, frames


def _silence_bytes(params: wave._wave_params, duration_ms: int) -> bytes:
    num_frames = int(params.framerate * duration_ms / 1000)
    bytes_per_frame = params.nchannels * params.sampwidth
    return b"\x00" * (num_frames * bytes_per_frame)


def _concat_wavs(wav_paths: List[Path], pauses: List[int], out_path: Path) -> None:
    base_params, first_frames = _read_wav(wav_paths[0])
    merged = bytearray(first_frames)
    if pauses[0]:
        merged.extend(_silence_bytes(base_params, pauses[0]))

    base_fmt = (
        base_params.nchannels,
        base_params.sampwidth,
        base_params.framerate,
        base_params.comptype,
    )
    for idx, wav_path in enumerate(wav_paths[1:], start=1):
        params, frames = _read_wav(wav_path)
        fmt = (params.nchannels, params.sampwidth, params.framerate, params.comptype)
        if fmt != base_fmt:
            raise ValueError(
                f"WAV format mismatch while merging: {wav_path.name} {fmt} != {base_fmt}"
            )
        merged.extend(frames)
        if pauses[idx]:
            merged.extend(_silence_bytes(base_params, pauses[idx]))

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(base_params.nchannels)
        wf.setsampwidth(base_params.sampwidth)
        wf.setframerate(base_params.framerate)
        wf.setcomptype(base_params.comptype, base_params.compname)
        wf.writeframes(bytes(merged))


# ---------------------------------------------------------------------------
# Transcript text dump
# ---------------------------------------------------------------------------


def _write_transcript_text(data: Dialogue, out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8") as f:
        header = f"{data.title}  [Part {data.part} / {data.difficulty}]"
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

        f.write("== Answer Key ==\n")
        for q in data.questions:
            f.write(f"Q{q.id}: {q.answer}\n")
        f.write("\n")

        f.write("== Key Phrases ==\n")
        kp_section = next(s for s in data.sections if s.type == "key_phrases")
        for i, line in enumerate(kp_section.lines[1:], start=1):
            f.write(f"{i:02d}. {line.text}\n")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def _flatten(sections: List[Section]) -> List[Tuple[int, str, Line, bool]]:
    out: List[Tuple[int, str, Line, bool]] = []
    idx = 1
    for section in sections:
        for i, line in enumerate(section.lines):
            is_last = i == len(section.lines) - 1
            out.append((idx, section.type, line, is_last))
            idx += 1
    return out


def run(
    client: OpenAI,
    dialogue_json: Path,
    *,
    outdir: Path,
    model: str,
    output_format: str,
    mp3_bitrate: str,
    work_dir: Path,
) -> Path:
    """Synthesize audio for the given Dialogue JSON.

    Per-line WAVs are written to a temp dir and removed at the end; only
    the concatenated result (MP3 or WAV) lands in ``outdir``. A human-
    readable transcript text is dumped to ``work_dir/transcript.txt``.
    """
    data = Dialogue.model_validate_json(dialogue_json.read_text(encoding="utf-8"))
    outdir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    flat = _flatten(data.sections)
    total = len(flat)

    with tempfile.TemporaryDirectory(prefix="toeic_tts_") as tmpdir:
        tmp = Path(tmpdir)
        wav_paths: List[Path] = []
        pauses: List[int] = []

        for (idx, stype, line, is_last) in flat:
            speaker_cfg = data.speakers[line.speaker]
            line_path = tmp / f"{idx:02d}_{stype}_{line.speaker}.wav"

            print(f"[{idx}/{total}] ({stype}) {line_path.name}")
            _synthesize_line(
                client,
                model=model,
                speaker_cfg=speaker_cfg,
                line=line,
                section_type=stype,
                out_path=line_path,
            )
            wav_paths.append(line_path)

            if is_last:
                pauses.append(SECTION_TRAILING_PAUSE_MS[stype])
            else:
                pauses.append(line.pause_ms_after)

        _write_transcript_text(data, work_dir / "transcript.txt")

        full_wav = tmp / f"{data.slug}_full.wav"
        _concat_wavs(wav_paths, pauses, full_wav)

        if output_format == "mp3":
            final_path = outdir / f"{data.slug}_full.mp3"
            print(f"Converting to MP3 ({mp3_bitrate}) ...")
            AudioSegment.from_wav(str(full_wav)).export(
                str(final_path), format="mp3", bitrate=mp3_bitrate
            )
        else:
            final_path = outdir / f"{data.slug}_full.wav"
            shutil.move(str(full_wav), str(final_path))

        print(f"\nDone: {final_path}")
        return final_path
