"""The window's open/reopen decision, which is what a user actually experiences.

The bug this locks down: the window runs as its own systemd unit, so "is the unit
active?" was used as a stand-in for "is the window on screen?". A process that
loses its window — a compositor restart, a surface that never mapped — leaves the
unit active and no window anywhere, and every later open then did nothing but
report success. The interesting cases are therefore all about the ghost.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from omarchy_voice import app  # noqa: E402


class FakeRun:
    """Records the subprocess calls open_window would make."""

    def __init__(self, clients=(), returncode=0, stderr="", stdout=""):
        self.clients = list(clients)
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        result = mock.Mock()
        result.returncode = self.returncode
        result.stderr = self.stderr
        if argv[:2] == ["hyprctl", "clients"]:
            result.stdout = json.dumps([{"class": c} for c in self.clients])
        else:
            result.stdout = self.stdout
        return result


class WindowPresent(unittest.TestCase):
    def test_a_window_of_ours_counts(self):
        with mock.patch.object(app.subprocess, "run", FakeRun(clients=["jarvis-voice"])):
            self.assertTrue(app.window_present())

    def test_someone_elses_window_does_not(self):
        with mock.patch.object(app.subprocess, "run", FakeRun(clients=["chromium", "kitty"])):
            self.assertFalse(app.window_present())

    def test_nothing_on_screen_does_not(self):
        with mock.patch.object(app.subprocess, "run", FakeRun(clients=[])):
            self.assertFalse(app.window_present())

    def test_a_broken_compositor_answer_does_not_crash_the_open(self):
        with mock.patch.object(app.subprocess, "run",
                               FakeRun(stdout="not json at all")):
            self.assertFalse(app.window_present())


class OpenWindow(unittest.TestCase):
    def _open(self, unit_active, clients, run=None):
        run = run or FakeRun(clients=clients)
        with mock.patch.object(app, "unit_active", return_value=unit_active), \
             mock.patch.object(app, "focus_window") as focus, \
             mock.patch.object(app, "close_window") as close, \
             mock.patch.object(app.subprocess, "run", run), \
             mock.patch.object(app.time, "sleep"):
            reply = app.open_window()
        return reply, focus, close, run

    def test_unit_up_with_a_window_raises_it_and_starts_nothing(self):
        reply, focus, close, run = self._open(True, ["jarvis-voice"])
        self.assertEqual(reply, "window already open")
        focus.assert_called_once()
        close.assert_not_called()
        self.assertFalse([c for c in run.calls if c[:1] == ["systemd-run"]])

    def test_unit_up_with_no_window_stops_the_ghost_and_starts_a_fresh_one(self):
        reply, focus, close, run = self._open(True, [])
        self.assertEqual(reply, "window opened")
        close.assert_called_once()          # the ghost is stopped, not trusted
        focus.assert_not_called()
        self.assertTrue([c for c in run.calls if c[:1] == ["systemd-run"]])

    def test_no_unit_starts_one(self):
        reply, focus, close, run = self._open(False, [])
        self.assertEqual(reply, "window opened")
        close.assert_not_called()
        self.assertTrue([c for c in run.calls if c[:1] == ["systemd-run"]])

    def test_a_failed_start_is_reported_not_swallowed(self):
        run = FakeRun(clients=[], returncode=1, stderr="Unit already exists")
        reply, _, _, _ = self._open(False, [], run=run)
        self.assertIn("Unit already exists", reply)


if __name__ == "__main__":
    unittest.main()
