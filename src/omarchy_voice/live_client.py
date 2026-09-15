"""Live transport with CLIENT delegation: GPT-Live speaks, Jarvis acts.

This is the fork's voice path. Upstream's ``live.py`` keeps OpenAI's hosted
backend (Responses delegation); here the session is created with
``delegation: {"type": "client"}``, so every request GPT-Live would delegate comes
to this process instead — and this process hands it to the Hermes agent through
:mod:`omarchy_voice.backend`.

    mic ─► session.input_audio.append ─► GPT-Live ─► session.delegation.created
                                                          │
                     session.commentary.append ◄── backend.ask(utterance)
                                                          │
    speaker ◄─ session.output_audio.delta ◄────────────────┘

The voice model never touches the desktop, and the backend never speaks. Both
halves stay honest because only verified backend text is appended back.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
import time
from collections import deque

from . import backend as backend_mod
from . import realtime
from .config import Config
from .feedback import Feedback
from .playback import LiveSpeaker
from .session import ControlServer
from .trace import Trace

LIVE_URL = "wss://api.openai.com/v1/live/sessions"
FRAME_BYTES = 4800                    # 100 ms of 24 kHz mono s16
START_TIMEOUT = 20.0
CLOSE_TIMEOUT = 15.0
ECHO_TAIL_SECONDS = 0.35
MAX_APPEND_CHARS = 1600               # the API caps one append at 500 tokens
CONTEXT_TURNS = 4

VOICE_PROMPT = """\
You are Jarvis, the voice of this Omarchy Linux desktop. You speak; a local
backend agent acts. Keep every spoken reply to one short sentence unless more
detail is asked for.

Speaking changes nothing. Every request that needs the desktop, the files,
information, or background work is delegated to the backend: it owns the tools,
the memory, the work queue and the permissions. Delegate new requests, including
requests that follow an error.

A backend result is an answer, not a new request. Say it in human words, and say
only what it actually reports: never add facts, never soften a failure into a
success, and never describe an action as done unless the result says it
completed. If the result says nothing happened, say that plainly.

If the backend needs a decision or a go-ahead, it will say so; put that question
to the user and wait — their next words are the answer. Never treat your own
speech as confirmation.

While the backend works, stay quiet unless it takes several seconds; then one
short line is enough. Never greet before the user speaks. Do not read out paths,
identifiers, or tool names. Wait for the user at session start.
"""


class ClientVoice:
    """One live voice session: audio in, delegations out, commentary back."""

    def __init__(self, config: Config):
        self.config = config
        self.feedback = Feedback(config)
        self.backend = backend_mod.Backend(
            command=config.backend_command,
            session=config.backend_session,
            model=config.backend_model,
            timeout_seconds=config.backend_timeout_seconds,
            extra_args=list(config.backend_extra_args),
        )
        self.trace = Trace(config.state_dir / "client-trace.jsonl")
        self.speaker = LiveSpeaker(config.live_sample_rate,
                                   buffer_ms=config.live_playback_buffer_ms,
                                   report=self._perf)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ws = None
        self.active = False                      # microphone open
        self.session_open = False
        self.epoch = 0
        self._wanted = asyncio.Event()           # a session is wanted
        self._stop = asyncio.Event()
        self._typed: asyncio.Queue[str] = asyncio.Queue()
        self._mic = None
        self._tasks: set[asyncio.Task] = set()
        self._history: deque[tuple[str, str]] = deque(maxlen=CONTEXT_TURNS * 2)
        self._input_text = ""
        self._output_text = ""
        self._usage_seconds = 0.0
        self._started_at = 0.0
        self._delegations = 0
        self._limit_notified = False
        self._mic_frames = 0
        self._muted = False

    # --- plumbing ---------------------------------------------------------

    def _trace(self, event: str, **values) -> None:
        try:
            self.trace.write(event, **values)
        except Exception:
            pass

    def _perf(self, event: str, **values) -> None:
        self._trace(f"playback.{event}", **values)

    def _state_file(self) -> str:
        status = ("listening" if self.active else
                  "idle" if self.session_open else "asleep")
        return json.dumps({
            "engine": "client",
            "status": status,
            "session": self.session_open,
            "microphone": self.active,
            "delegations": self._delegations,
            "usage_seconds": round(self._usage_seconds, 1),
            "backend": self.backend.session,
            "backend_available": not self.backend.available(),
        })

    def _control(self, command: str) -> str:
        """Called from the control socket thread."""
        words = (command or "").strip().split(maxsplit=1)
        verb = words[0].lower() if words else "status"
        rest = words[1].strip() if len(words) > 1 else ""
        if self.loop is None:
            return json.dumps({"error": "not running"})
        if verb in ("status", "state"):
            return self._state_file()
        if verb in ("toggle", "start", "stop", "quit", "mute", "unmute", "say", "listen"):
            action = verb
            text = rest
            if verb == "listen":
                action = rest or "status"
                text = ""
            asyncio.run_coroutine_threadsafe(self._command(action, text), self.loop)
            return json.dumps({"ok": True, "queued": action})
        if verb in ("confirm", "cancel"):
            return json.dumps({"ok": False,
                               "detail": "confirmations are spoken, in conversation"})
        return json.dumps({"error": f"unknown command: {verb}"})

    async def _command(self, action: str, text: str) -> None:
        if action in ("toggle", "start"):
            if self._wanted.is_set():
                if action == "toggle":
                    await self._close_session("toggled off")
                else:
                    self._wanted.set()
            else:
                self._wanted.set()
                self.feedback.log("gate    session requested")
        elif action in ("stop", "quit"):
            await self._close_session(action)
        elif action == "mute":
            self._muted = True
            self.active = False
            await self._kill_mic()
            self.feedback.state("idle", "muted")
        elif action == "unmute":
            self._muted = False
            if self.session_open:
                self.active = True
        elif action == "say" and text:
            await self._typed.put(text)
        elif action == "status":
            self.feedback.log(self._state_file())

    async def _close_session(self, why: str) -> None:
        self._wanted.clear()
        self.active = False
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps({"type": "session.close"}))
            except Exception:
                pass
        self.feedback.state("idle", why)
        self._trace("session.close_requested", why=why)

    # --- session ----------------------------------------------------------

    def _session_start(self) -> dict:
        key = os.environ.get(self.config.api_key_env, "")
        history = [{"type": "message", "role": role, "content": [
            {"type": "input_text" if role == "user" else "output_text", "text": text}]}
            for role, text in self._history]
        return {"type": "session.start", "session": {
            "model": self.config.live_model,
            "instructions": VOICE_PROMPT,
            "store": False,
            "input": history,
            "audio": {"format": {"type": "audio/pcm", "rate": self.config.live_sample_rate},
                      "output": {"voice": self.config.live_voice}},
            "delegation": {"type": "client"},
        }}

    async def _send(self, payload: dict) -> None:
        if self.ws is None:
            return
        await self.ws.send(json.dumps(payload))

    async def _append(self, kind: str, text: str, delegation_id) -> None:
        text = (text or "").strip()
        if not text:
            return
        await self._send({
            "type": f"session.{kind}.append",
            "event_id": f"{kind}_{int(time.time() * 1000)}",
            "delegation_id": delegation_id,
            "content": text[:MAX_APPEND_CHARS],
        })
        self._trace(f"append.{kind}", chars=len(text), delegation=delegation_id or "")

    # --- audio ------------------------------------------------------------

    async def _audio_loop(self) -> None:
        rate = self.config.live_sample_rate
        pending = b""
        try:
            while not self._stop.is_set() and self.session_open:
                self.speaker.check_error()
                if self.active:
                    if self._mic is None:
                        command = ["pw-record", "--rate", str(rate), "--channels", "1",
                                   "--format", "s16", "--latency", "20ms"]
                        if self.config.device:
                            command += ["--target", self.config.device]
                        self._mic = await asyncio.create_subprocess_exec(
                            *command, "-", stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.DEVNULL)
                    stdout = self._mic.stdout
                    if stdout is None:
                        raise RuntimeError("pw-record has no stdout")
                    chunk = await stdout.read(rate // 10 * 2)
                    if not chunk:
                        if self.active:
                            raise RuntimeError("pw-record ended unexpectedly")
                        return
                else:
                    await asyncio.sleep(0.1)
                    chunk = bytes(rate // 10 * 2)
                if self._stop.is_set() or not self.session_open:
                    return
                chunk = pending + chunk
                # Keep the stream paced with whole frames; silence while muted.
                frames = []
                while len(chunk) >= FRAME_BYTES:
                    frames.append(chunk[:FRAME_BYTES])
                    chunk = chunk[FRAME_BYTES:]
                pending = chunk
                speaking = self.speaker.is_playing(int(ECHO_TAIL_SECONDS))
                for frame in frames:
                    if speaking and not self.config.barge_in:
                        frame = bytes(len(frame))
                    if self.active:
                        self.feedback.level(realtime.frame_level(frame),
                                            self.speaker.level_now())
                    await self._send({"type": "session.input_audio.append",
                                      "audio": base64.b64encode(frame).decode()})
                    self._mic_frames += 1
                    await asyncio.sleep(FRAME_BYTES / 2 / rate)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._trace("audio.error", error=f"{type(exc).__name__}: {exc}")
            self.feedback.log(f"error   audio {type(exc).__name__}: {exc}")
            self._wanted.clear()

    # --- events -----------------------------------------------------------

    async def _on_event(self, event: dict) -> None:
        etype = event.get("type", "")
        if etype == "session.delegation.created":
            delegation = event.get("delegation", {}) or {}
            delegation_id = delegation.get("id")
            utterance = self._input_text.strip()
            self._input_text = ""
            self._delegations += 1
            self._trace("delegation.created", target=delegation.get("target"),
                        delegation=delegation_id or "", utterance=utterance[:200])
            if delegation_id:
                self._spawn(self._delegate(delegation_id, utterance))
        elif etype == "session.input_transcript.delta":
            self._input_text += event.get("delta", "")
        elif etype == "session.output_transcript.delta":
            self._output_text += event.get("delta", "")
        elif etype == "session.output_audio.delta":
            data = event.get("delta") or ""
            if data:
                await self.speaker.write(base64.b64decode(data))
        elif etype == "session.usage.updated":
            usage = event.get("usage") or event.get("session") or {}
            seconds = usage.get("seconds") if isinstance(usage, dict) else None
            if isinstance(seconds, (int, float)):
                self._usage_seconds = float(seconds)
            self._trace("usage", payload=json.dumps(event)[:300])
        elif etype in ("error", "session.error"):
            self.feedback.log(f"error   live {json.dumps(event)[:200]}")
            self._trace("session.error", payload=json.dumps(event)[:400])
        elif etype.endswith(".appended"):
            self._trace("append.acked", kind=etype,
                        client_event_id=event.get("client_event_id", ""))
        elif etype in ("session.closed",):
            self._trace("session.closed", reason=event.get("reason", ""))

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _delegate(self, delegation_id: str, utterance: str) -> None:
        """Run one backend turn and hand the verified text back to the voice."""
        if not utterance:
            utterance = "(the user spoke; no transcript reached this process)"
        self.feedback.state("thinking", utterance[:60])
        context = "\n".join(f"{role}: {text}" for role, text in self._history)
        reply = await self.backend.ask(utterance, context=context)
        self._trace("backend.turn", ok=reply.ok, seconds=round(reply.seconds, 2),
                    utterance=utterance[:200], answer=reply.text[:300],
                    error=reply.raw_error[:200])
        if not reply.ok:
            self.feedback.log(f"error   backend {reply.raw_error[:160]}")
        self._history.append(("user", utterance))
        self._history.append(("assistant", reply.text))
        await self._append("commentary", reply.text, delegation_id)
        self.feedback.state("listening" if self.active else "idle")

    async def _typed_loop(self) -> None:
        """`listen say "..."` — the backend directly, spoken by the voice model."""
        while not self._stop.is_set():
            text = await self._typed.get()
            if not text:
                continue
            self.feedback.state("thinking", text[:60])
            reply = await self.backend.ask(text, context="")
            self.feedback.state("listening" if self.active else "idle")
            self._trace("backend.typed", ok=reply.ok, seconds=round(reply.seconds, 2),
                        answer=reply.text[:300])
            self._history.append(("user", text))
            self._history.append(("assistant", reply.text))
            if self.session_open:
                await self._append("commentary", reply.text, None)
            else:
                # No session to speak it: say so in the state the bar widget and
                # `status --json` read, rather than answering into the void.
                self.feedback.state("idle", reply.text[:80])
                self.feedback.log(f"say     {reply.text[:200]}")

    # --- connection -------------------------------------------------------

    async def _connection(self, headers: dict) -> None:
        self.epoch += 1
        epoch = self.epoch
        self._input_text = self._output_text = ""
        self._mic_frames = 0
        await self.speaker.start()
        async with realtime._open_socket(LIVE_URL, headers) as ws:
            self.ws = ws
            await self._send(self._session_start())
            event = json.loads(await asyncio.wait_for(ws.recv(), START_TIMEOUT))
            if event.get("type") != "session.started":
                raise RuntimeError(f"session.start refused: {json.dumps(event)[:300]}")
            self.session_open = True
            # A session opens for speaking, so the microphone follows it —
            # unless the user muted while it was still connecting.
            if not self._muted:
                self.active = True
            self._started_at = time.monotonic()
            self._limit_notified = False
            self._trace("session.started", id=event.get("session", {}).get("id", ""))
            self.feedback.state("listening" if self.active else "idle")
            audio = asyncio.create_task(self._audio_loop())
            usage = asyncio.create_task(self._housekeeping())
            try:
                while not self._stop.is_set() and self._wanted.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 1.0)
                    except asyncio.TimeoutError:
                        continue
                    await self._on_event(json.loads(raw))
                    if epoch != self.epoch:
                        break
            finally:
                audio.cancel()
                usage.cancel()
                for task in (audio, usage):
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
                self.session_open = False
                self.ws = None
                self._history.append(("assistant", self._output_text.strip()))
                self._output_text = ""
                await self._kill_mic()

    async def _housekeeping(self) -> None:
        """Session limit and a slow-backend notice."""
        limit = self.config.live_max_session_seconds
        while self.session_open and not self._stop.is_set():
            await asyncio.sleep(1.0)
            if limit and time.monotonic() - self._started_at >= limit and not self._limit_notified:
                self._limit_notified = True
                self.feedback.notify("Voice session limit reached",
                                     "Listening stopped; toggle to start again.")
                await self._close_session("session limit reached")

    async def _kill_mic(self) -> None:
        proc, self._mic = self._mic, None
        if proc is None:
            return
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), 5.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # --- entry point ------------------------------------------------------

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        key = os.environ.get(self.config.api_key_env)
        if not key:
            raise realtime.RealtimeUnavailable(
                f"{self.config.api_key_env} is not set")
        problem = self.backend.available()
        if problem:
            raise realtime.RealtimeUnavailable(f"backend unusable: {problem}")
        headers = {"Authorization": f"Bearer {key}",
                   "OpenAI-Safety-Identifier": realtime._safety_identifier()}
        control = ControlServer(self._control)
        control.start()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                self.loop.add_signal_handler(signum, self._stop.set)
            except (NotImplementedError, RuntimeError, ValueError):
                pass
        typed = asyncio.create_task(self._typed_loop())
        attempts = 0
        self.feedback.state("idle")
        self.feedback.log(f"gate    Live + client delegation; backend '{self.backend.session}'")
        try:
            while not self._stop.is_set():
                if not self._wanted.is_set():
                    await asyncio.sleep(0.1)
                    continue
                before = time.monotonic()
                try:
                    await self._connection(headers)
                    attempts = 0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.feedback.log(f"error   live {type(exc).__name__}: {exc}")
                    self._trace("connection.error", error=f"{type(exc).__name__}: {exc}")
                    healthy = time.monotonic() - before >= realtime.RECONNECT_HEALTHY_SECONDS
                    attempts = 0 if (healthy and self._usage_seconds) else attempts + 1
                    if attempts > realtime.RECONNECT_ATTEMPTS:
                        self.active = False
                        self._wanted.clear()
                        self.feedback.notify("Voice connection failed",
                                             "Toggle to try again.")
                        attempts = 0
                    elif self._wanted.is_set():
                        await asyncio.sleep(min(2.0 * attempts, 15.0))
        finally:
            typed.cancel()
            self._wanted.clear()
            self.active = False
            await self._kill_mic()
            control.stop()
            self.feedback.state("idle", "stopped")


def run(config: Config) -> int:
    voice = ClientVoice(config)
    try:
        asyncio.run(voice.run())
    except realtime.RealtimeUnavailable as exc:
        print(f"jarvis-voice: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0
    return 0
