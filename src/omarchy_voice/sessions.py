"""Voice sessions and the jobs they started. SQLite, one file, no server.

A session is the unit the listener actually thinks in: he presses the key, talks,
Jarvis starts background work, and later he presses **new session** to draw a line
under all of it — the jobs stop, the board empties, and the next conversation
starts with no memory of the last one.

Who writes what, and why it is split this way:

* the **daemon** owns the session lifecycle — it is the only part that knows when
  a session is really open — so it opens a row when a session starts and closes it
  when it ends;
* the **window** discovers jobs in Paperclip (titles marked ``[Jarvis]``, created
  after the session started) and records what it saw, so a board can survive a
  restart of either process, and a stop has issue ids to work with;
* nothing else writes. One writer per fact, the same rule the rest of this machine
  runs on.

The database lives beside the other state (``~/.local/state/jarvis-voice``), mode
600, and holds no credentials — only session names, times and job identifiers.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .config import STATE_DIR

DB_FILE = STATE_DIR / "sessions.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    started_at  REAL NOT NULL,
    ended_at    REAL
);
CREATE TABLE IF NOT EXISTS jobs (
    identifier  TEXT PRIMARY KEY,
    issue_id    TEXT NOT NULL,
    session_id  INTEGER NOT NULL REFERENCES sessions(id),
    title       TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    seen_at     REAL NOT NULL,
    stopped_at  REAL
);
CREATE INDEX IF NOT EXISTS jobs_by_session ON jobs(session_id);
"""


@dataclass
class JobRecord:
    identifier: str
    issue_id: str
    title: str
    status: str
    created_at: float
    stopped_at: float | None = None


def session_name(when: float | None = None, topic: str = "Voice session") -> str:
    """`[Jarvis] <topic> · 2026-09-15 15:20` — the name every session carries."""
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(when or time.time()))
    return f"[Jarvis] {topic.strip() or 'Voice session'} · {stamp}"


class Sessions:
    def __init__(self, path: Path | str = DB_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The daemon reads this from the event loop and from worker threads
        # (`asyncio.to_thread`), and sqlite3 refuses a connection used across
        # threads unless it is told to allow it. One lock, every statement, so
        # "allow" cannot turn into "race".
        self._play_lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), timeout=10,
                                   check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._play_lock:
            self._db.executescript(SCHEMA)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    # --- sessions ---------------------------------------------------------

    def open(self, name: str | None = None, at: float | None = None) -> int:
        """Start a session, closing any that was left open."""
        now = at or time.time()
        self.close()
        with self._play_lock:
            cursor = self._db.execute(
                "INSERT INTO sessions (name, started_at) VALUES (?, ?)",
                (name or session_name(now), now))
            self._db.commit()
            return int(cursor.lastrowid or 0)

    def close(self, session_id: int | None = None) -> int:
        """Close the given session (or the open one). Returns how many were open."""
        with self._play_lock:
            if session_id is None:
                cursor = self._db.execute(
                    "UPDATE sessions SET ended_at = ? WHERE ended_at IS NULL",
                    (time.time(),))
            else:
                cursor = self._db.execute(
                    "UPDATE sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
                    (time.time(), session_id))
            self._db.commit()
            return cursor.rowcount

    def current(self) -> sqlite3.Row | None:
        with self._play_lock:
            return self._db.execute(
                "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()

    def ensure(self, name: str | None = None) -> sqlite3.Row:
        row = self.current()
        if row is None:
            self.open(name)
            row = self.current()
        assert row is not None
        return row

    def recent(self, limit: int = 10) -> list[sqlite3.Row]:
        with self._play_lock:
            return self._db.execute(
                "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    # --- jobs -------------------------------------------------------------

    def record(self, session_id: int, identifier: str, issue_id: str, title: str,
               status: str, created_at: float) -> None:
        with self._play_lock:
            self._db.execute(
                """INSERT INTO jobs (identifier, issue_id, session_id, title, status,
                                 created_at, seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(identifier) DO UPDATE SET
                 status = excluded.status,
                 title = excluded.title,
                 seen_at = excluded.seen_at""",
                (identifier, issue_id, session_id, title, status, created_at,
                 time.time()))
            self._db.commit()

    def jobs(self, session_id: int, include_stopped: bool = False) -> list[JobRecord]:
        sql = "SELECT * FROM jobs WHERE session_id = ?"
        if not include_stopped:
            sql += " AND stopped_at IS NULL"
        sql += " ORDER BY created_at DESC"
        with self._play_lock:
            rows = self._db.execute(sql, (session_id,)).fetchall()
        return [JobRecord(r["identifier"], r["issue_id"], r["title"], r["status"],
                          r["created_at"], r["stopped_at"]) for r in rows]

    def mark_stopped(self, identifier: str) -> None:
        with self._play_lock:
            self._db.execute("UPDATE jobs SET stopped_at = ? WHERE identifier = ?",
                             (time.time(), identifier))
            self._db.commit()

    def forget_session(self, session_id: int) -> None:
        """Drop a session's job rows — used when its jobs were stopped and cleared."""
        with self._play_lock:
            self._db.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
            self._db.commit()
