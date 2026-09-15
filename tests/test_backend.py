"""Backend adapter tests. Offline: every turn runs a fake command, never Hermes."""

from __future__ import annotations

import asyncio
import os
import stat
import tempfile
import unittest
from pathlib import Path

from omarchy_voice.backend import (Backend, EMPTY_TEXT, FAILURE_TEXT, TIMEOUT_TEXT,
                                   VOICE_TURN_CONTRACT)


def script(body: str, name: str = "fake-agent") -> str:
    """A fake backend command: ignores its arguments, runs ``body``."""
    directory = tempfile.mkdtemp()
    path = Path(directory) / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


class CleanTests(unittest.TestCase):
    def test_strips_markdown_and_hermes_notices(self):
        backend = Backend()
        raw = ("⚠ A previous `hermes update` pulled new code\n"
               "  Run `hermes update` or `hermes gateway restart`.\n"
               "# Heading\n\n**Done.** The window is on *workspace three*.\n")
        self.assertEqual(backend.clean(raw), "Heading Done. The window is on workspace three.")

    def test_caps_length_on_a_word_boundary(self):
        backend = Backend(max_chars=20)
        out = backend.clean("one two three four five six seven")
        self.assertLessEqual(len(out), 21)
        self.assertTrue(out.endswith("…"))

    def test_empty_input_stays_empty(self):
        self.assertEqual(Backend().clean(""), "")

    def test_compose_carries_contract_context_and_utterance(self):
        prompt = Backend().compose("move it to workspace three", context="user: hello")
        self.assertIn(VOICE_TURN_CONTRACT.splitlines()[0], prompt)
        self.assertIn("user: hello", prompt)
        self.assertIn("move it to workspace three", prompt)


class AvailabilityTests(unittest.TestCase):
    def test_missing_command_is_reported_not_raised(self):
        backend = Backend(command="definitely-not-a-real-command-xyz")
        self.assertIn("not found on PATH", backend.available())

    def test_empty_command_is_reported(self):
        self.assertIn("no backend command", Backend(command="").available())

    def test_real_command_is_available(self):
        self.assertEqual(Backend(command=script("echo ok")).available(), "")

    def test_turn_argv_uses_oneshot_and_named_session(self):
        argv = Backend(command="hermes", session="jarvis-voice",
                       model="deepseek-flash").turn_argv("hi")
        self.assertEqual(argv[:2], ["hermes", "-z"])
        self.assertIn("--continue", argv)
        self.assertEqual(argv[argv.index("--continue") + 1], "jarvis-voice")
        self.assertEqual(argv[argv.index("-m") + 1], "deepseek-flash")

    def test_create_argv_bootstraps_the_named_session(self):
        argv = Backend(session="jarvis-voice").create_argv()
        self.assertEqual(argv[:2], ["hermes", "chat"])
        self.assertIn("--create-if-missing", argv)


class AskTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_answer_is_returned(self):
        backend = Backend(command=script('echo "Switched to workspace 2."'))
        reply = await backend.ask("go to workspace two")
        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, "Switched to workspace 2.")
        self.assertEqual(reply.raw_error, "")

    async def test_timeout_says_nothing_was_done(self):
        backend = Backend(command=script("sleep 5"), timeout_seconds=0.4)
        reply = await backend.ask("do a slow thing")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.text, TIMEOUT_TEXT)
        self.assertEqual(reply.raw_error, "timeout")

    async def test_nonzero_exit_is_a_failure_not_an_answer(self):
        backend = Backend(command=script("exit 3"))
        reply = await backend.ask("anything")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.text, FAILURE_TEXT)

    async def test_empty_output_is_a_failure(self):
        backend = Backend(command=script("exit 0"))
        reply = await backend.ask("anything")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.text, EMPTY_TEXT)

    async def test_missing_session_is_created_then_the_turn_retried(self):
        # First call (-z ... --continue) fails like Hermes does; the chat call creates it.
        body = (
            'if [ "$1" = "chat" ]; then\n'
            '  cat > /dev/null\n'
            '  exit 0\n'
            'fi\n'
            'echo "No session found matching \'jarvis-voice\'." >&2\n'
            'echo "No session found matching \'jarvis-voice\'."\n'
            'exit 1\n'
        )
        # Second run of the same argv succeeds, so wrap the script in a counter.
        directory = tempfile.mkdtemp()
        counter = Path(directory) / "count"
        path = Path(directory) / "fake-agent"
        path.write_text(
            "#!/bin/sh\n"
            f"n=$(cat {counter} 2>/dev/null || echo 0)\n"
            f"echo $((n+1)) > {counter}\n"
            'if [ "$1" = "chat" ]; then cat > /dev/null; exit 0; fi\n'
            'if [ "$n" -eq 0 ]; then\n'
            '  echo "No session found matching" >&2\n'
            '  echo "No session found matching"\n'
            '  exit 1\n'
            'fi\n'
            'echo "Created and answered."\n')
        path.chmod(0o755)
        backend = Backend(command=str(path), timeout_seconds=30)
        reply = await backend.ask("first turn")
        self.assertTrue(reply.ok, reply.raw_error)
        self.assertEqual(reply.text, "Created and answered.")
        # Three invocations: the failed turn, the `chat` bootstrap, the retry.
        self.assertEqual(int(counter.read_text().strip()), 3)

    async def test_unavailable_backend_never_raises(self):
        backend = Backend(command="/nonexistent/agent")
        reply = await backend.ask("hello")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.text, FAILURE_TEXT)
        self.assertIn("not found on PATH", reply.raw_error)

    async def test_ask_records_elapsed_time(self):
        backend = Backend(command=script("echo ok"))
        reply = await backend.ask("hi")
        self.assertGreater(reply.seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
