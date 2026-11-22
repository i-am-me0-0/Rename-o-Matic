import unittest
from pathlib import Path
from unittest.mock import patch

from actions.series import _episode_offset_rows, _find_episode_offset_candidate


class EpisodeOffsetTests(unittest.TestCase):
    def setUp(self):
        self.files = [
            (Path("Show S04E01.mkv"), 4, 1, ""),
            (Path("Show S04E02.mkv"), 4, 2, ""),
        ]
        self.source_map = {
            1: "tt0000001",
            2: "tt0000002",
            3: "tt0000003",
        }

    def test_special_at_first_source_episode_is_a_candidate(self):
        titles = {
            "tt0000001": "Holiday Special",
            "tt0000002": "Regular Episode 1",
            "tt0000003": "Regular Episode 2",
        }
        with patch("actions.series._episode_title_for_id", titles.get):
            candidate = _find_episode_offset_candidate(
                self.files,
                {"show": {4: self.source_map}},
                "show",
            )

        self.assertIsNotNone(candidate)

    def test_offset_rows_show_proposed_source_titles(self):
        titles = {
            "tt0000002": "Regular Episode 1",
            "tt0000003": "Regular Episode 2",
        }
        with patch("actions.series._episode_title_for_id", titles.get):
            rows = _episode_offset_rows(self.files, self.source_map, 1)

        self.assertEqual(rows[0][0:3], (1, 2, "Regular Episode 1"))
        self.assertEqual(rows[1][0:3], (2, 3, "Regular Episode 2"))

    def test_adjacent_titles_detect_unlabelled_special_offset(self):
        titles = {
            "tt0000001": "Nathan for You: A Celebration",
            "tt0000002": "The Richards Tip",
            "tt0000003": "Chili Shop Massage Parlor",
        }
        files = [
            (Path("Show S04E01 - The Richards Tip.mkv"), 4, 1, ""),
            (Path("Show S04E02 - Chili Shop Massage Parlor.mkv"), 4, 2, ""),
        ]
        with patch("actions.series._episode_title_for_id", titles.get):
            candidate = _find_episode_offset_candidate(
                files,
                {"show": {4: {1: "tt0000001", 2: "tt0000002", 3: "tt0000003"}}},
                "show",
            )

        self.assertIsNotNone(candidate)


if __name__ == "__main__":
    unittest.main()
