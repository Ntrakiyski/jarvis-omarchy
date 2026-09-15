"""Background jobs, read from the local Paperclip server.

The window shows the jobs **of the current voice session**. Paperclip is the work
plane: every durable job Jarvis starts — a build, a research pass, a hardening
task — is an issue whose title carries a marker, and this module is the read-only
view of them, plus the one write the listener needs: stop.

Loopback only, and no credentials: the server on 127.0.0.1 answers company reads
*and* issue writes to the local user, so neither the window nor the daemon holds a
key. Only the URL and company id are read from ``~/.hermes/.env`` — never the
secrets in that file.

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

# Every job Jarvis starts carries this marker in its title, so a session's board
# can show exactly those and nothing else: "[Jarvis] <topic> · 2026-09-15 14:52".
MARKER = "[Jarvis]"

HERMES_ENV = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / ".env"
DEFAULT_URL = "http://127.0.0.1:3100"
CACHE_SECONDS = 3.0

COLUMNS = (
    ("working", "Working", ("todo", "in_progress", "backlog"), True),
    ("needs", "Needs you", ("blocked", "in_review"), True),
    ("done", "Done", ("done",), False),
    ("cancelled", "Cancelled", ("cancelled",), False),
)
STOPPABLE = {key for key, _, _, stoppable in COLUMNS if stoppable}
STATUS_LABEL = {
    "todo": "queued", "backlog": "backlog", "in_progress": "running",
    "in_review": "in review", "blocked": "blocked", "done": "done",
    "cancelled": "cancelled",
}
STATUS_TONE = {
    "todo": "dim", "backlog": "dim", "in_progress": "go", "in_review": "warn",
    "blocked": "bad", "done": "ok", "cancelled": "dim",
}


def is_marked(title: str) -> bool:
    return title.strip().lower().startswith(MARKER.lower())


def job_title(topic: str, when=None) -> str:
    """The name every job Jarvis creates must carry."""
    import datetime
    stamp = (when or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M")
    return f"{MARKER} {topic.strip()} · {stamp}"


@dataclass
class Card:
    identifier: str
    title: str
    status: str
    updated: float
    priority: str = ""
    agent: str = ""
    issue_id: str = ""
    column: str = "working"
    created: float = 0.0

    @property
    def label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    @property
    def tone(self) -> str:
        return STATUS_TONE.get(self.status, "dim")

    @property
    def stoppable(self) -> bool:
        return self.column in STOPPABLE

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
    session_name: str = ""
    window_start: float = 0.0

    @property
    def total(self) -> int:
        return sum(len(cards) for _, _, cards in self.columns)

    @property
    def active(self) -> int:
        return sum(len(cards) for key, _, cards in self.columns if key in STOPPABLE)


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


def _patch(url: str, body: dict, timeout: float = 10.0):
    request = urllib.request.Request(url, method="PATCH",
                                     data=json.dumps(body).encode(),
                                     headers={"Accept": "application/json",
                                              "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class Jobs:
    """Reads the session's board, stops a job, remembers the last good read."""

    def __init__(self, base_url: str = "", company_id: str = ""):
        self.base_url = (base_url or _env_value("PAPERCLIP_API_URL", DEFAULT_URL)).rstrip("/")
        self.company_id = company_id or _env_value("PAPERCLIP_COMPANY_ID", "")
        self._agents: dict[str, str] = {}
        self._cache: Board | None = None
        self._at = 0.0
        self._since = -1.0

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

    def marked(self, since: float = 0.0) -> list[dict]:
        """Marked issues created at or after `since`, newest first."""
        company = self._company()
        issues = _get(f"{self.base_url}/api/companies/{company}/issues")
        if isinstance(issues, dict):
            issues = issues.get("issues", [])
        agents = self._agent_names(company)
        out = []
        for issue in issues:
            title = " ".join(str(issue.get("title", "")).split())
            if not is_marked(title):
                continue
            created = _epoch(issue.get("createdAt") or issue.get("updatedAt"))
            if since and created < since:
                continue
            out.append({
                "issue_id": str(issue.get("id", "")),
                "identifier": str(issue.get("identifier") or issue.get("id", ""))[:12],
                "title": title[:200],
                "status": str(issue.get("status", "todo")),
                "created_at": created,
                "updated": _epoch(issue.get("updatedAt") or issue.get("createdAt")),
                "priority": str(issue.get("priority") or ""),
                "agent": agents.get(issue.get("assigneeAgentId") or "", ""),
            })
        out.sort(key=lambda item: item["created_at"], reverse=True)
        return out

    def stop(self, issue_id: str) -> tuple[bool, str]:
        """Cancel one job. No credentials: the local user may write."""
        if not issue_id:
            return False, "no issue id"
        try:
            _patch(f"{self.base_url}/api/issues/{issue_id}", {"status": "cancelled"})
            return True, "cancelled"
        except urllib.error.HTTPError as exc:
            return False, f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, f"{type(exc).__name__}"

    def stop_marked_since(self, since: float) -> list[str]:
        """Cancel every marked job created since `since`; returns what was stopped."""
        stopped = []
        for item in self.marked(since):
            if item["status"] in ("done", "cancelled"):
                continue
            ok, _detail = self.stop(item["issue_id"])
            if ok:
                stopped.append(item["identifier"])
        return stopped

    # --- the board --------------------------------------------------------

    def fetch(self, since: float = 0.0, force: bool = False) -> Board:
        # The cache belongs to one window: a new session changes `since`, and
        # reusing the old board would record the previous session's jobs into the
        # new one — which is exactly the thing "new session" is supposed to clear.
        if (not force and self._cache and self._since == since
                and (time.monotonic() - self._at) < CACHE_SECONDS):
            return self._cache
        try:
            items = self.marked(since)
        except (urllib.error.URLError, ValueError, OSError, RuntimeError) as exc:
            board = Board(error=f"Paperclip unreachable ({type(exc).__name__})",
                          columns=self._cache.columns if self._cache else [],
                          session_name=self._cache.session_name if self._cache else "",
                          window_start=since)
            self._cache = board
            self._at = time.monotonic()
            return board

        cards = [Card(identifier=item["identifier"], title=item["title"],
                      status=item["status"], updated=item["updated"],
                      priority=item["priority"], agent=item["agent"],
                      issue_id=item["issue_id"], created=item["created_at"])
               for item in items]
        columns = []
        for key, heading, statuses, _stoppable in COLUMNS:
            in_column = [c for c in cards if c.status in statuses]
            for card in in_column:
                card.column = key
            in_column.sort(key=lambda c: c.updated, reverse=True)
            columns.append((key, heading, in_column))
        self._cache = Board(columns=columns, fetched_at=time.time(),
                            window_start=since)
        self._at = time.monotonic()
        self._since = since
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
