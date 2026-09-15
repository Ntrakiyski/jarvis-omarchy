"""Background jobs, read from the local Paperclip server.

The window shows these as a kanban. Paperclip is the work plane: every durable
job Jarvis starts — a build, a research pass, a hardening task — is an issue with
a status, and this module is the read-only view of it.

Loopback only, and no credentials: the server on 127.0.0.1 answers company reads
to the local user, so the UI never holds a key. Only the URL and the company id
are read from ``~/.hermes/.env`` (never the secrets in that file).

The four columns are the four things a person can act on:

* **working**  — running or queued: todo, in_progress, backlog
* **needs you** — the job is stopped on a decision: blocked, in_review
* **done**     — finished
* **cancelled** — stopped on purpose

Cards carry the *real* status word (blocked, in review, queued…), so folding
in_review into "needs you" cannot hide what Paperclip actually thinks.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERMES_ENV = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / ".env"
DEFAULT_URL = "http://127.0.0.1:3100"
CACHE_SECONDS = 5.0

COLUMNS = (
    ("working", "Working", ("todo", "in_progress", "backlog")),
    ("needs", "Needs you", ("blocked", "in_review")),
    ("done", "Done", ("done",)),
    ("cancelled", "Cancelled", ("cancelled",)),
)
STATUS_LABEL = {
    "todo": "queued", "backlog": "backlog", "in_progress": "running",
    "in_review": "in review", "blocked": "blocked", "done": "done",
    "cancelled": "cancelled",
}
STATUS_TONE = {
    "todo": "dim", "backlog": "dim", "in_progress": "go", "in_review": "warn",
    "blocked": "bad", "done": "ok", "cancelled": "dim",
}


@dataclass
class Card:
    identifier: str
    title: str
    status: str
    updated: float
    priority: str = ""
    agent: str = ""
    url: str = ""

    @property
    def label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def tone(self) -> str:
        return STATUS_TONE.get(self.status, "dim")

    @property
    def age(self) -> str:
        seconds = max(0.0, time.time() - self.updated)
        if seconds < 90:
            return "just now"
        if seconds < 5400:
            return f"{int(seconds // 60)} min ago"
        if seconds < 172800:
            return f"{int(seconds // 3600)} h ago"
        return f"{int(seconds // 86400)} d ago"


@dataclass
class Board:
    columns: list[tuple[str, str, list[Card]]] = field(default_factory=list)
    error: str = ""
    fetched_at: float = 0.0

    @property
    def total(self) -> int:
        return sum(len(cards) for _, _, cards in self.columns)


def _env_value(name: str, default: str = "") -> str:
    """Process environment first, then ~/.hermes/.env — no secrets are read."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in HERMES_ENV.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def _get(url: str, timeout: float = 8.0):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class Jobs:
    """Reads the board, and remembers the last good one."""

    def __init__(self, base_url: str = "", company_id: str = ""):
        self.base_url = (base_url or _env_value("PAPERCLIP_API_URL", DEFAULT_URL)).rstrip("/")
        self.company_id = company_id or _env_value("PAPERCLIP_COMPANY_ID", "")
        self._agents: dict[str, str] = {}
        self._cache: Board | None = None
        self._at = 0.0

    # --- api ---------------------------------------------------------------

    def _company(self) -> str:
        if self.company_id:
            return self.company_id
        companies = _get(f"{self.base_url}/api/companies")
        if not companies:
            raise RuntimeError("no companies on the local Paperclip server")
        self.company_id = companies[0]["id"]
        return self.company_id

    def _agent_names(self, company: str) -> dict[str, str]:
        if self._agents:
            return self._agents
        try:
            agents = _get(f"{self.base_url}/api/companies/{company}/agents")
        except (urllib.error.URLError, ValueError, OSError):
            return {}
        for agent in agents if isinstance(agents, list) else agents.get("agents", []):
            name = agent.get("name") or agent.get("title") or ""
            if name:
                self._agents[agent.get("id", "")] = name
        return self._agents

    def fetch(self, force: bool = False) -> Board:
        if not force and self._cache and (time.monotonic() - self._at) < CACHE_SECONDS:
            return self._cache
        try:
            company = self._company()
            issues = _get(f"{self.base_url}/api/companies/{company}/issues")
            if isinstance(issues, dict):
                issues = issues.get("issues", [])
            agents = self._agent_names(company)
        except (urllib.error.URLError, ValueError, OSError, RuntimeError) as exc:
            board = Board(error=f"Paperclip unreachable ({type(exc).__name__})",
                          columns=self._cache.columns if self._cache else [])
            self._cache = board
            self._at = time.monotonic()
            return board

        cards = []
        for issue in issues:
            status = str(issue.get("status", "todo"))
            title = " ".join(str(issue.get("title", "")).split())
            cards.append(Card(
                identifier=str(issue.get("identifier") or issue.get("id", ""))[:12],
                title=title[:160],
                status=status,
                updated=_epoch(issue.get("updatedAt") or issue.get("createdAt")),
                priority=str(issue.get("priority") or ""),
                agent=agents.get(issue.get("assigneeAgentId") or "", ""),
                url=f"{self.base_url}/company/issues/{issue.get('id','')}",
            ))

        columns = []
        for key, heading, statuses in COLUMNS:
            in_column = [c for c in cards if c.status in statuses]
            in_column.sort(key=lambda c: c.updated, reverse=True)
            columns.append((key, heading, in_column))
        self._cache = Board(columns=columns, fetched_at=time.time())
        self._at = time.monotonic()
        return self._cache


def _epoch(value) -> float:
    if isinstance(value, (int, float)):
        return float(value) / (1000 if value > 1e11 else 1)
    if isinstance(value, str) and value:
        try:
            from datetime import datetime
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0
