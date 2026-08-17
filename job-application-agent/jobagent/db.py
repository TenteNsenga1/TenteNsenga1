"""SQLite-backed store for the job application pipeline.

Pipeline statuses, in order: new -> scored -> excluded (dead end)
                                      -> materials_ready -> applied
                                      -> interviewing -> offer / rejected
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL,
    location TEXT,
    remote INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    tags TEXT,
    category TEXT,
    ai_score REAL NOT NULL DEFAULT 0,
    exclusion_hits TEXT,
    fit_score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    notes TEXT,
    materials_path TEXT,
    applied_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_fit_score ON jobs(fit_score);
"""

VALID_STATUSES = {
    "new",
    "scored",
    "excluded",
    "materials_ready",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    location: str = ""
    remote: bool = True
    description: str = ""
    tags: str = ""
    category: Optional[str] = None
    ai_score: float = 0.0
    exclusion_hits: str = ""
    fit_score: float = 0.0
    status: str = "new"
    notes: str = ""
    materials_path: Optional[str] = None
    applied_at: Optional[str] = None
    id: Optional[int] = None


def upsert_job(conn: sqlite3.Connection, job: Job) -> tuple[int, bool]:
    """Insert a job, ignoring it if (source, external_id) already exists.

    Returns (row_id, was_new).
    """
    now = _now()
    cur = conn.execute(
        "SELECT id FROM jobs WHERE source = ? AND external_id = ?",
        (job.source, job.external_id),
    )
    existing = cur.fetchone()
    if existing:
        return existing["id"], False

    cur = conn.execute(
        """
        INSERT INTO jobs (
            source, external_id, title, company, url, location, remote,
            description, tags, category, ai_score, exclusion_hits, fit_score,
            status, notes, materials_path, applied_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.source,
            job.external_id,
            job.title,
            job.company,
            job.url,
            job.location,
            int(job.remote),
            job.description,
            job.tags,
            job.category,
            job.ai_score,
            job.exclusion_hits,
            job.fit_score,
            job.status,
            job.notes,
            job.materials_path,
            job.applied_at,
            now,
            now,
        ),
    )
    return cur.lastrowid, True


def update_job(conn: sqlite3.Connection, job_id: int, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    conn.execute(f"UPDATE jobs SET {columns} WHERE id = ?", values)


def set_status(conn: sqlite3.Connection, job_id: int, status: str, **extra: Any) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unknown status '{status}'. Valid: {sorted(VALID_STATUSES)}")
    if status == "applied" and "applied_at" not in extra:
        extra["applied_at"] = _now()
    update_job(conn, job_id, status=status, **extra)


def get_job(conn: sqlite3.Connection, job_id: int) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return cur.fetchone()


def list_jobs(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    min_fit_score: Optional[float] = None,
    order_by: str = "fit_score DESC",
    limit: Optional[int] = None,
) -> list[sqlite3.Row]:
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if min_fit_score is not None:
        query += " AND fit_score >= ?"
        params.append(min_fit_score)
    query += f" ORDER BY {order_by}"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    cur = conn.execute(query, params)
    return cur.fetchall()


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    cur = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
    return {row["status"]: row["n"] for row in cur.fetchall()}
