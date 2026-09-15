"""The session store: one open session, its jobs, and what forgetting means."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omarchy_voice.sessions import Sessions, session_name


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Sessions(Path(self.dir.name) / "sessions.db")

    def tearDown(self):
        self.dir.cleanup()

    def test_a_session_carries_the_naming_he_asked_for(self):
        name = session_name(when=1757937600, topic="Voice session")
        self.assertTrue(name.startswith("[Jarvis] Voice session · "))
        self.assertRegex(name, r"· \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_opening_closes_whatever_was_open(self):
        first = self.store.open("first")
        second = self.store.open("second")
        self.assertEqual(self.store.current()["id"], second)
        rows = {r["id"]: r["ended_at"] for r in self.store.recent(5)}
        self.assertIsNotNone(rows[first])
        self.assertIsNone(rows[second])

    def test_ensure_reuses_the_open_session(self):
        row = self.store.ensure("only")
        self.assertEqual(self.store.ensure("ignored")["id"], row["id"])
        self.assertEqual(len(self.store.recent(5)), 1)

    def test_close_reports_whether_anything_was_open(self):
        self.store.open("one")
        self.assertEqual(self.store.close(), 1)
        self.assertEqual(self.store.close(), 0)

    def test_jobs_are_recorded_once_and_updated_in_place(self):
        sid = self.store.open("s")
        self.store.record(sid, "FRA-1", "id-1", "[Jarvis] a", "todo", 1000.0)
        self.store.record(sid, "FRA-1", "id-1", "[Jarvis] a", "in_progress", 1000.0)
        rows = self.store.jobs(sid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "in_progress")

    def test_stopping_hides_the_row_but_keeps_the_record(self):
        sid = self.store.open("s")
        self.store.record(sid, "FRA-1", "id-1", "[Jarvis] a", "in_progress", 1000.0)
        self.store.mark_stopped("FRA-1")
        self.assertEqual(self.store.jobs(sid), [])
        self.assertEqual(len(self.store.jobs(sid, include_stopped=True)), 1)

    def test_forgetting_a_session_drops_its_jobs_only(self):
        first = self.store.open("s1")
        self.store.record(first, "FRA-1", "id-1", "[Jarvis] a", "todo", 1000.0)
        self.store.close(first)
        second = self.store.open("s2")
        self.store.record(second, "FRA-2", "id-2", "[Jarvis] b", "todo", 2000.0)
        self.store.forget_session(first)
        self.assertEqual(self.store.jobs(first), [])
        self.assertEqual([j.identifier for j in self.store.jobs(second)], ["FRA-2"])

    def test_the_database_is_private(self):
        import stat
        mode = stat.S_IMODE(Path(self.store.path).stat().st_mode)
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
