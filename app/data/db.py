"""Capa de persistencia SQLite para la cola de trabajo y la configuración."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "VozATexto"
DB_PATH = APP_SUPPORT_DIR / "queue.db"
MODELS_DIR = APP_SUPPORT_DIR / "models"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    display_name TEXT NOT NULL,
    model TEXT NOT NULL,
    language TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | running | done | error | canceled
    progress REAL NOT NULL DEFAULT 0.0,       -- 0..1
    duration_seconds REAL,                    -- duración del audio, se conoce al empezar
    elapsed_seconds REAL NOT NULL DEFAULT 0.0,
    speed_realtime REAL,                      -- factor x tiempo real (duration/elapsed)
    error_message TEXT,
    output_dir TEXT,
    result_json_path TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "max_parallel": "3",
    "ram_reserved_per_worker_mb": "2200",
    "ram_safety_margin_mb": "1500",
    "output_dir": str(Path.home() / "Documents" / "Transcripciones"),
    "default_model": "large-v3-turbo",
    "language": "es",
}


@dataclass
class Job:
    id: Optional[int]
    source_path: str
    display_name: str
    model: str
    language: Optional[str]
    status: str = "pending"
    progress: float = 0.0
    duration_seconds: Optional[float] = None
    elapsed_seconds: float = 0.0
    speed_realtime: Optional[float] = None
    error_message: Optional[str] = None
    output_dir: Optional[str] = None
    result_json_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    position: int = 0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Job":
        return cls(**{k: row[k] for k in row.keys()})


class Database:
    def __init__(self, path: Path = DB_PATH):
        APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._seed_settings()

    def _seed_settings(self) -> None:
        cur = self._conn.cursor()
        for key, value in DEFAULT_SETTINGS.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
        self._conn.commit()

    # ---- settings ----
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self._conn.commit()

    def all_settings(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ---- jobs ----
    def add_job(self, job: Job) -> int:
        max_pos = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS m FROM jobs"
        ).fetchone()["m"]
        job.position = max_pos + 1
        cur = self._conn.execute(
            """INSERT INTO jobs
               (source_path, display_name, model, language, status, progress,
                duration_seconds, elapsed_seconds, speed_realtime, error_message,
                output_dir, result_json_path, created_at, started_at, finished_at, position)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job.source_path, job.display_name, job.model, job.language,
                job.status, job.progress, job.duration_seconds, job.elapsed_seconds,
                job.speed_realtime, job.error_message, job.output_dir,
                job.result_json_path, job.created_at, job.started_at, job.finished_at,
                job.position,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_job(self, job_id: int, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [job_id]
        self._conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", values)
        self._conn.commit()

    def delete_job(self, job_id: int) -> None:
        self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        self._conn.commit()

    def get_job(self, job_id: int) -> Optional[Job]:
        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job.from_row(row) if row else None

    def list_jobs(self) -> list[Job]:
        rows = self._conn.execute("SELECT * FROM jobs ORDER BY position ASC").fetchall()
        return [Job.from_row(r) for r in rows]

    def pending_jobs(self) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = 'pending' ORDER BY position ASC"
        ).fetchall()
        return [Job.from_row(r) for r in rows]

    def reset_running_to_pending(self) -> None:
        """Al reabrir la app: los que quedaron 'running' vuelven a la cola."""
        self._conn.execute(
            "UPDATE jobs SET status = 'pending', progress = 0.0, elapsed_seconds = 0.0 "
            "WHERE status = 'running'"
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
