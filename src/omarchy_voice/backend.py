"""The Jarvis backend behind the voice model.

GPT-Live owns the spoken conversation; this module owns the thinking. Each
delegation is one turn in a named Hermes session, so conversation state, skills,
memory and the work plane stay on this machine — and the cloud never sees the
tools, the files, or the task state, only the words it is asked to say.

Nothing is invented. A turn that times out, exits non-zero, or answers with no
text is reported to the listener as a failure: the voice model may paraphrase a
result, so a wrong result must never look like a successful one.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from dataclasses import dataclass, field

# Prepended to every turn. Short on purpose: the session already carries the
# conversation, and every extra word is paid for on each delegation.
VOICE_TURN_CONTRACT = """\
Voice call turn. Answer for speech: at most two short sentences, plain words, no
markdown, no lists, no paths. Say only what a tool result confirmed this turn. If
nothing was done, say that. If an irreversible action is wanted, ask for a
go-ahead in one line and wait for it.

Any background job you start is titled exactly "[Jarvis] <topic> · <YYYY-MM-DD
HH:MM>" — the window's board shows only those, and the name is how the listener
tells your work from everything else in the work plane.
"""

TIMEOUT_TEXT = "The backend did not answer in time, so nothing was done."
FAILURE_TEXT = "The backend could not be reached, so nothing was done."
EMPTY_TEXT = "The backend returned no answer, so nothing was done."

_NOISE = re.compile(r"^\s*(⚠|Run `hermes)(.*)$", re.MULTILINE)


@dataclass
class BackendReply:
    """One backend turn. ``ok`` is False whenever the text is not a real answer."""

    ok: bool
    text: str
    seconds: float = 0.0
    raw_error: str = ""


@dataclass
class Backend:
    """Runs the configured agent command and returns what it said."""

    command: str = "hermes"
    session: str = "jarvis-voice"
    model: str = ""
    timeout_seconds: float = 120.0
    extra_args: list[str] = field(default_factory=list)
    max_chars: int = 1500
    bootstrap_text: str = "Reply with exactly: ready"
    # What this voice session is, and what it has started — so the backend has the
    # same picture the listener is looking at.
    session_label: str = ""
    session_jobs: list[str] = field(default_factory=list)

    def available(self) -> str:
        """Empty when the backend looks usable, else the reason it does not."""
        if not self.command:
            return "no backend command configured"
        if not shutil.which(self.command):
            return f"backend command not found on PATH: {self.command}"
        return ""

    # --- command lines ----------------------------------------------------

    def turn_argv(self, prompt: str) -> list[str]:
        argv = [self.command, "-z", prompt, "--continue", self.session]
        if self.model:
            argv += ["-m", self.model]
        return argv + list(self.extra_args)

    def create_argv(self) -> list[str]:
        argv = [self.command, "chat", "--continue", self.session,
                "--create-if-missing", "--cli"]
        if self.model:
            argv += ["-m", self.model]
        return argv + list(self.extra_args)

    def compose(self, utterance: str, context: str = "") -> str:
        parts = [VOICE_TURN_CONTRACT]
        if self.session_label:
            line = f"# This voice session\n{self.session_label}"
            if self.session_jobs:
                line += ("\nJobs you started in it, which the listener can stop from "
                         "the board: " + ", ".join(self.session_jobs))
            else:
                line += "\nNo background jobs started in it yet."
            parts.append(line)
        if context.strip():
            parts.append("# The last few things said out loud\n" + context.strip()[:800])
        parts.append("# What the user just said\n" + utterance.strip())
        return "\n\n".join(parts)

    # --- cleaning ---------------------------------------------------------

    def clean(self, text: str) -> str:
        text = _NOISE.sub("", text or "")
        text = text.replace("```", " ")
        text = re.sub(r"[*_`#>]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > self.max_chars:
            text = text[: self.max_chars].rsplit(" ", 1)[0] + "…"
        return text

    # --- running ----------------------------------------------------------

    async def ask(self, utterance: str, context: str = "") -> BackendReply:
        """One turn. Never raises: every failure comes back as a spoken-able fact."""
        problem = self.available()
        if problem:
            return BackendReply(False, FAILURE_TEXT, raw_error=problem)
        started = time.monotonic()
        reply = await self._run_turn(self.compose(utterance, context))
        if not reply.ok and "No session found matching" in (reply.raw_error or ""):
            await self._create_session()
            reply = await self._run_turn(self.compose(utterance, context))
        reply.seconds = time.monotonic() - started
        return reply

    async def _run_turn(self, prompt: str) -> BackendReply:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.turn_argv(prompt),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
        except OSError as exc:
            return BackendReply(False, FAILURE_TEXT, raw_error=str(exc))
        try:
            out, err = await asyncio.wait_for(proc.communicate(), self.timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await proc.wait()
            except Exception:
                pass
            return BackendReply(False, TIMEOUT_TEXT, raw_error="timeout")
        text = self.clean(out.decode(errors="replace"))
        errors = err.decode(errors="replace").strip()
        if proc.returncode != 0:
            return BackendReply(False, FAILURE_TEXT, raw_error=errors or f"exit {proc.returncode}")
        if not text:
            return BackendReply(False, EMPTY_TEXT, raw_error=errors or "empty answer")
        return BackendReply(True, text)

    async def _create_session(self) -> bool:
        """Create the named session once, so later turns can continue it."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.create_argv(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
        except OSError:
            return False
        try:
            await asyncio.wait_for(
                proc.communicate((self.bootstrap_text + "\n").encode()), 90.0)
        except asyncio.TimeoutError:
            proc.kill()
            return False
        return proc.returncode == 0
