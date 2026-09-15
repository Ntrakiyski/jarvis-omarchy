"""Opt-in probe: does this account accept CLIENT delegation on GPT-Live?

Opens one paid Live session (``v1/live/sessions``), speaks a synthetic desktop
request from a raw PCM file, and reports whether the session accepts
``delegation: {"type": "client"}``, whether ``session.delegation.created``
arrives, whether ``session.commentary.append`` is accepted, and whether the
voice model then speaks the appended result.

It never opens a microphone, never plays audio, and never touches the desktop:
the only input is a file you pass in, and the only "backend" is a canned string.

    ffmpeg -i phrase.mp3 -ar 24000 -ac 1 -f s16le phrase.pcm
    python tools/check_client_delegation.py --connect --pcm phrase.pcm

Costs roughly 30 seconds of Live session time plus no backend calls.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import time
from pathlib import Path

LIVE_URL = "wss://api.openai.com/v1/live/sessions"
FRAME_BYTES = 4800            # 100 ms of 24 kHz mono s16
SILENCE_FRAMES = 15           # 1.5 s of trailing silence so the turn can end
DELEGATION_WAIT = 25.0
REPLY_WAIT = 25.0
CANNED_REPLY = ("The window is on workspace three. This was a transport test, "
                "so nothing actually moved.")

VOICE_INSTRUCTIONS = (
    "You are testing delegation. The user speaks a desktop request. Ask the "
    "backend for help by delegating; the backend has the desktop tools and you "
    "do not. Then say its result out loud in one short sentence."
)


def api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    env = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "jarvis-voice" / "env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("no OPENAI_API_KEY in the environment or in ~/.config/jarvis-voice/env")


async def probe(pcm: Path, voice: str, sample_rate: int):
    import websockets

    headers = {"Authorization": f"Bearer {api_key()}"}
    seen: dict[str, int] = {}
    delegation_id = None
    out_transcript: list[str] = []
    audio_bytes = 0
    started = time.monotonic()

    def note(event: dict) -> None:
        seen[event["type"]] = seen.get(event["type"], 0) + 1

    async with websockets.connect(LIVE_URL, additional_headers=headers,
                                  max_size=None, open_timeout=20) as ws:
        session = {
            "model": "gpt-live-1",
            "instructions": VOICE_INSTRUCTIONS,
            "store": False,
            "audio": {"format": {"type": "audio/pcm", "rate": sample_rate},
                      "output": {"voice": voice}},
            "delegation": {"type": "client"},
        }
        await ws.send(json.dumps({"type": "session.start", "session": session}))
        first = json.loads(await asyncio.wait_for(ws.recv(), 20))
        note(first)
        print(f"session.start -> {first.get('type')}")
        if first.get("type") != "session.started":
            print("RAW:", json.dumps(first)[:600])
            return 1
        print(f"session id: {first.get('session', {}).get('id', '?')}")

        data = pcm.read_bytes()
        print(f"speaking {len(data)/2/sample_rate:.1f}s of synthesized audio")
        for off in range(0, len(data), FRAME_BYTES):
            frame = data[off:off + FRAME_BYTES]
            await ws.send(json.dumps({
                "type": "session.input_audio.append",
                "audio": base64.b64encode(frame).decode()}))
            await asyncio.sleep(FRAME_BYTES / 2 / sample_rate)
        for _ in range(SILENCE_FRAMES):
            await ws.send(json.dumps({
                "type": "session.input_audio.append",
                "audio": base64.b64encode(bytes(FRAME_BYTES)).decode()}))
            await asyncio.sleep(0.1)

        deadline = time.monotonic() + DELEGATION_WAIT
        speaking_deadline = None
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), 1.0)
            except asyncio.TimeoutError:
                continue
            event = json.loads(raw)
            note(event)
            etype = event.get("type", "")
            if etype == "session.delegation.created":
                delegation = event.get("delegation", {})
                delegation_id = delegation.get("id")
                print(f"delegation.created -> target={delegation.get('target')!r} "
                      f"id={delegation_id!r} offset_ms={event.get('offset_ms')}")
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    "type": "session.commentary.append",
                    "event_id": "probe_reply_1",
                    "delegation_id": delegation_id,
                    "content": CANNED_REPLY}))
                print("commentary.append sent")
                speaking_deadline = time.monotonic() + REPLY_WAIT
                deadline = speaking_deadline
            elif etype == "session.output_transcript.delta":
                out_transcript.append(event.get("delta", ""))
            elif etype == "session.output_audio.delta":
                audio_bytes += len(base64.b64decode(event.get("delta", "") or ""))
            elif etype.endswith(".appended"):
                print(f"{etype} (client_event_id={event.get('client_event_id')})")
            elif etype in ("error", "session.error"):
                print("ERROR event:", json.dumps(event)[:400])
            if speaking_deadline and audio_bytes and etype == "session.output_transcript.delta":
                pass

        await ws.send(json.dumps({"type": "session.close"}))
        try:
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), 5))
                note(event)
                if event.get("type") in ("session.closed", "session.usage.updated"):
                    print("close:", event.get("type"), json.dumps(event)[:200])
                if event.get("type") == "session.closed":
                    break
        except (asyncio.TimeoutError, Exception):
            pass

    print("\n--- event census ---")
    for name, count in sorted(seen.items()):
        print(f"  {count:>3}  {name}")
    print("\n--- verdict ---")
    print(f"client delegation accepted : {'session.delegation.created' in seen}")
    print(f"delegation id seen         : {delegation_id is not None}")
    print(f"commentary accepted        : {'session.commentary.appended' in seen}")
    print(f"model spoke after append   : {audio_bytes > 0} ({audio_bytes} bytes of audio)")
    print(f"spoken transcript          : {''.join(out_transcript)[:400]!r}")
    print(f"elapsed                    : {time.monotonic() - started:.1f}s "
          f"(~${(time.monotonic() - started) / 60 * 0.05:.4f} of Live time)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--connect", action="store_true",
                        help="authorize the paid API probe (required)")
    parser.add_argument("--pcm", required=True, type=Path,
                        help="raw 24 kHz mono s16le PCM file of the request to speak")
    parser.add_argument("--voice", default="marin")
    parser.add_argument("--rate", type=int, default=24000)
    args = parser.parse_args()
    if not args.connect:
        print("This probe opens a paid Live session. Re-run with --connect.")
        return 2
    if not args.pcm.exists():
        print(f"missing PCM file: {args.pcm}")
        return 2
    return asyncio.run(probe(args.pcm, args.voice, args.rate))


if __name__ == "__main__":
    raise SystemExit(main())
