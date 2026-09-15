"""The jobs board: marker, naming, and the filter that keeps the board honest."""

from __future__ import annotations

import unittest
from datetime import datetime

from omarchy_voice import jobs
from omarchy_voice.jobs import Card, Jobs, is_marked, job_title


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
        built = job_title("Bootstrap kit", datetime(2026, 9, 15, 15, 4))
        self.assertEqual(built, "[Jarvis] Bootstrap kit · 2026-09-15 15:04")

    def test_job_title_strips_topic_whitespace(self):
        self.assertTrue(job_title("  spaced  ", datetime(2026, 1, 2, 3, 4)).startswith("[Jarvis] spaced ·"))


def issue(identifier, title, status="todo", updated="2026-09-15T12:00:00Z"):
    return {"id": identifier, "identifier": identifier, "title": title,
            "status": status, "updatedAt": updated, "assigneeAgentId": "a1"}


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.issues = [
            issue("FRA-1", "[Jarvis] Bootstrap kit · 2026-09-15 15:04", "todo"),
            issue("FRA-2", "[self-improve] harden terminal", "done"),
            issue("FRA-3", "[Jarvis] Read the paper · 2026-09-15 15:10", "blocked"),
            issue("FRA-4", "PROBE-do-not-keep", "cancelled"),
        ]
        self.fake_get = lambda url, timeout=8.0: (
            self.issues if url.endswith("/issues") else [{"id": "a1", "name": "Engineer"}])
        self.real_get = jobs._get

    def tearDown(self):
        jobs._get = self.real_get

    def board(self, only_marked):
        jobs._get = self.fake_get
        reader = Jobs(base_url="http://127.0.0.1:3100", company_id="c",
                      only_marked=only_marked)
        return reader.fetch(force=True)

    def test_default_board_shows_only_marked_jobs(self):
        board = self.board(True)
        self.assertEqual(board.total, 2)
        self.assertEqual(board.skipped, 2)
        ids = [card.identifier for _, _, cards in board.columns for card in cards]
        self.assertEqual(sorted(ids), ["FRA-1", "FRA-3"])

    def test_columns_map_statuses_the_way_the_board_promises(self):
        board = self.board(True)
        by_key = {key: [c.identifier for c in cards] for key, _, cards in board.columns}
        self.assertEqual(by_key["working"], ["FRA-1"])
        self.assertEqual(by_key["needs"], ["FRA-3"])
        self.assertEqual(by_key["done"], [])
        self.assertEqual(by_key["cancelled"], [])

    def test_unfiltered_board_shows_everything(self):
        board = self.board(False)
        self.assertEqual(board.total, 4)
        self.assertEqual(board.skipped, 0)

    def test_a_dead_server_keeps_the_last_good_board(self):
        good = self.board(True)
        self.assertEqual(good.total, 2)

        def boom(url, timeout=8.0):
            raise OSError("connection refused")

        jobs._get = boom
        reader = Jobs(base_url="http://127.0.0.1:3100", company_id="c", only_marked=True)
        reader._cache = good
        broken = reader.fetch(force=True)
        self.assertTrue(broken.error)
        self.assertEqual(broken.total, 2)  # the board does not empty itself


class CardTests(unittest.TestCase):
    def test_every_status_has_a_label_and_a_tone(self):
        for status in ("todo", "backlog", "in_progress", "in_review", "blocked",
                       "done", "cancelled"):
            card = Card("FRA-9", "x", status, 0.0)
            self.assertTrue(card.label, status)
            self.assertTrue(card.tone, status)

    def test_age_reads_in_plain_words(self):
        import time
        now = time.time()
        self.assertEqual(Card("F", "t", "done", now - 10).age, "just now")
        self.assertEqual(Card("F", "t", "done", now - 600).age, "10 min ago")
        self.assertEqual(Card("F", "t", "done", now - 7200).age, "2 h ago")
        self.assertEqual(Card("F", "t", "done", now - 200000).age, "2 d ago")


if __name__ == "__main__":
    unittest.main()
