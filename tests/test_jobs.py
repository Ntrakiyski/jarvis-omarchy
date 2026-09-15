"""The jobs board: the marker, the session window, and stopping a job."""

from __future__ import annotations

import unittest
import urllib.error
from datetime import datetime, timezone

from omarchy_voice import jobs
from omarchy_voice.jobs import Card, Jobs, is_marked, job_title


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def issue(identifier, title, status="todo", created=0.0, updated=None):
    return {"id": f"id-{identifier}", "identifier": identifier, "title": title,
            "status": status, "assigneeAgentId": "a1",
            "createdAt": iso(created), "updatedAt": iso(updated or created)}


NOW = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc).timestamp()
OLD = NOW - 86400


class NamingTests(unittest.TestCase):
    def test_marker_is_recognised_case_insensitively_and_after_padding(self):
        self.assertTrue(is_marked("[Jarvis] Build the kit · 2026-09-15 15:00"))
        self.assertTrue(is_marked("  [jarvis] lowercase"))
        self.assertTrue(is_marked("[JARVIS] shouted"))

    def test_other_titles_are_not_marked(self):
        for title in ("Self-improve: harden terminal", "[jarvis-voice] old style",
                      "Investigate [Jarvis] in the middle", ""):
            self.assertFalse(is_marked(title), title)

    def test_job_title_shape(self):
        self.assertEqual(job_title("Bootstrap kit", datetime(2026, 9, 15, 15, 4)),
                         "[Jarvis] Bootstrap kit · 2026-09-15 15:04")


class WindowTests(unittest.TestCase):
    """The board shows this session's jobs — the ones created after it started."""

    def setUp(self):
        self.issues = [
            issue("FRA-1", "[Jarvis] This session's build · x", "in_progress", created=NOW),
            issue("FRA-2", "[Jarvis] Yesterday's build · y", "done", created=OLD),
            issue("FRA-3", "[self-improve] someone else's work", "done", created=NOW),
        ]
        self.real_get = jobs._get
        jobs._get = lambda url, timeout=8.0: (
            self.issues if url.endswith("/issues") else [{"id": "a1", "name": "Engineer"}])

    def tearDown(self):
        jobs._get = self.real_get

    def reader(self):
        return Jobs(base_url="http://x", company_id="c")

    def test_only_this_session_and_only_marked(self):
        board = self.reader().fetch(since=NOW, force=True)
        ids = [c.identifier for _, _, cards in board.columns for c in cards]
        self.assertEqual(ids, ["FRA-1"])

    def test_without_a_window_every_marked_job_shows(self):
        board = self.reader().fetch(since=0.0, force=True)
        ids = sorted(c.identifier for _, _, cards in board.columns for c in cards)
        self.assertEqual(ids, ["FRA-1", "FRA-2"])

    def test_columns_map_statuses_the_way_the_board_promises(self):
        board = self.reader().fetch(since=0.0, force=True)
        by_key = {key: [c.identifier for c in cards] for key, _, cards in board.columns}
        self.assertEqual(by_key["working"], ["FRA-1"])
        self.assertEqual(by_key["done"], ["FRA-2"])
        self.assertEqual(by_key["needs"], [])
        self.assertEqual(board.active, 1)

    def test_the_cache_does_not_leak_across_session_windows(self):
        reader = self.reader()
        old_window = reader.fetch(since=OLD, force=True)
        self.assertEqual(old_window.total, 2)
        fresh_window = reader.fetch(since=NOW)      # a new session started
        self.assertEqual([c.identifier for _, _, cards in fresh_window.columns
                          for c in cards], ["FRA-1"])

    def test_a_dead_server_keeps_the_last_good_board(self):
        good = self.reader().fetch(since=NOW, force=True)
        self.assertEqual(good.total, 1)

        def boom(url, timeout=8.0):
            raise OSError("connection refused")

        jobs._get = boom
        broken = self.reader().fetch(since=NOW, force=True)
        self.assertTrue(broken.error)


class StopTests(unittest.TestCase):
    def setUp(self):
        self.real_get, self.real_patch = jobs._get, jobs._patch
        self.issues = [
            issue("FRA-1", "[Jarvis] running one", "in_progress", created=NOW),
            issue("FRA-2", "[Jarvis] finished one", "done", created=NOW),
        ]
        jobs._get = lambda url, timeout=8.0: (
            self.issues if url.endswith("/issues") else [{"id": "a1", "name": "Engineer"}])
        self.patched: list[tuple[str, dict]] = []

    def tearDown(self):
        jobs._get, jobs._patch = self.real_get, self.real_patch

    def test_stop_sends_a_cancel(self):
        jobs._patch = lambda url, body, timeout=10.0: self.patched.append((url, body)) or {}
        ok, detail = Jobs(base_url="http://x", company_id="c").stop("id-FRA-1")
        self.assertTrue(ok)
        self.assertEqual(self.patched, [("http://x/api/issues/id-FRA-1",
                                         {"status": "cancelled"})])

    def test_stop_reports_an_http_error_instead_of_raising(self):
        def boom(url, body, timeout=10.0):
            raise urllib.error.HTTPError(url, 403, "nope", {}, None)

        jobs._patch = boom
        ok, detail = Jobs(base_url="http://x", company_id="c").stop("id-FRA-1")
        self.assertFalse(ok)
        self.assertIn("403", detail)

    def test_stop_marked_since_leaves_finished_jobs_alone(self):
        jobs._patch = lambda url, body, timeout=10.0: self.patched.append((url, body)) or {}
        stopped = Jobs(base_url="http://x", company_id="c").stop_marked_since(NOW)
        self.assertEqual(stopped, ["FRA-1"])
        self.assertEqual(len(self.patched), 1)


class ActiveCountTests(unittest.TestCase):
    def test_only_unfinished_work_counts_as_active(self):
        items = [{"status": "todo"}, {"status": "in_progress"}, {"status": "blocked"},
                 {"status": "in_review"}, {"status": "backlog"}, {"status": "done"},
                 {"status": "cancelled"}]
        self.assertEqual(jobs.active_jobs(items), 5)

    def test_an_empty_board_is_zero(self):
        self.assertEqual(jobs.active_jobs([]), 0)


class CardTests(unittest.TestCase):
    def test_every_status_has_a_label_and_a_tone(self):
        for status in ("todo", "backlog", "in_progress", "in_review", "blocked",
                       "done", "cancelled"):
            card = Card("FRA-9", "x", status, 0.0)
            self.assertTrue(card.label, status)
            self.assertTrue(card.tone, status)

    def test_only_active_columns_offer_a_stop(self):
        self.assertTrue(Card("F", "t", "in_progress", 0.0, column="working").stoppable)
        self.assertTrue(Card("F", "t", "blocked", 0.0, column="needs").stoppable)
        self.assertFalse(Card("F", "t", "done", 0.0, column="done").stoppable)
        self.assertFalse(Card("F", "t", "cancelled", 0.0, column="cancelled").stoppable)

    def test_age_reads_in_plain_words(self):
        import time
        now = time.time()
        self.assertEqual(Card("F", "t", "done", now - 10).age, "just now")
        self.assertEqual(Card("F", "t", "done", now - 600).age, "10 min ago")
        self.assertEqual(Card("F", "t", "done", now - 7200).age, "2 h ago")
        self.assertEqual(Card("F", "t", "done", now - 200000).age, "2 d ago")


if __name__ == "__main__":
    unittest.main()
