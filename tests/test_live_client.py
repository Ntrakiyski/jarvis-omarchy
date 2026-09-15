"""The pause lifecycle, which is what user-visible "start does nothing" really is.

The bug this locks down: ``_muted``/``_paused_at`` lived on the client, not on the
session. Pause once and every later session opened already muted — no recorder, no
"listening", and then the stale pause clock killed it as "paused too long" while it
was still billing. Offline: no network, no audio, no backend process.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from omarchy_voice.config import Config  # noqa: E402
from omarchy_voice.live_client import ClientVoice  # noqa: E402


def client() -> ClientVoice:
    config = Config(state_dir=Path(tempfile.mkdtemp()))
    return ClientVoice(config)


class PauseLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_a_closed_session_takes_its_pause_with_it(self):
        voice = client()
        voice.session_open = True
        voice._muted = True
        voice._paused_at = 12345.0

        await voice._close_session("stop")

        self.assertFalse(voice._muted, "the next session would open muted")
        self.assertEqual(voice._paused_at, 0.0, "the pause clock would still be running")

    async def test_pause_keeps_the_session_but_close_releases_it(self):
        voice = client()
        voice.session_open = True

        await voice._command("pause", "")

        self.assertTrue(voice._muted)          # the take survives, the mic does not
        self.assertFalse(voice.active)

        await voice._command("stop", "")

        self.assertFalse(voice._muted, "a new session must start with a live microphone")

    async def test_housekeeping_cannot_kill_a_session_that_was_paused_long_ago(self):
        """The exact ghost: a pause from a previous session closing the new one."""
        voice = client()
        voice.session_open = True
        voice._muted = True
        voice._paused_at = 0.0                 # cleared by _close_session
        voice.config.live_paused_idle_seconds = 120.0

        # What housekeeping tests: muted AND a pause clock past the limit.
        stale = (voice._muted and voice._paused_at
                 and 1e6 - voice._paused_at >= voice.config.live_paused_idle_seconds)
        self.assertFalse(stale, "housekeeping would close a fresh session immediately")

    async def test_start_when_a_session_is_already_wanted_is_a_no_op(self):
        voice = client()
        seen = []
        voice.feedback.log = lambda line: seen.append(line)   # type: ignore[assignment]

        await voice._command("start", "")
        await voice._command("start", "")

        self.assertTrue(voice._wanted.is_set())
        self.assertEqual(len(seen), 1, "the second start must not queue a second session")

    async def test_toggle_off_closes_a_wanted_session(self):
        voice = client()
        voice._wanted.set()

        await voice._command("toggle", "")

        self.assertFalse(voice._wanted.is_set())


if __name__ == "__main__":
    unittest.main()
