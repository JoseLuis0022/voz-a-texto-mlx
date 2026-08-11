"""Genera los archivos de salida (TXT, SRT, JSON) a partir del resultado de mlx_whisper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(segments: list[dict[str, Any]]) -> str:
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _format_srt_timestamp(seg["start"])
        end = _format_srt_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def write_outputs(
    *,
    result: dict[str, Any],
    source_path: Path,
    output_dir: Path,
    model_key: str,
    elapsed_seconds: float,
    duration_seconds: float,
) -> dict[str, Path]:
    """Escribe .txt, .srt y .json junto con metadata de ingeniería. Devuelve las rutas."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source_path.stem

    txt_path = output_dir / f"{stem}.txt"
    srt_path = output_dir / f"{stem}.srt"
    json_path = output_dir / f"{stem}.json"

    text = result.get("text", "").strip()
    segments = result.get("segments", [])
    language = result.get("language")

    txt_path.write_text(text + "\n", encoding="utf-8")
    srt_path.write_text(build_srt(segments), encoding="utf-8")

    speed_realtime = (duration_seconds / elapsed_seconds) if elapsed_seconds > 0 else None
    metadata = {
        "source_file": str(source_path),
        "model": model_key,
        "language_detected": language,
        "duration_seconds": duration_seconds,
        "processing_seconds": elapsed_seconds,
        "speed_realtime_factor": speed_realtime,
        "segment_count": len(segments),
    }
    payload = {
        "metadata": metadata,
        "text": text,
        "segments": segments,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"txt": txt_path, "srt": srt_path, "json": json_path}
