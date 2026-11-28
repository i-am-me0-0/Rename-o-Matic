import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from actions.series import (
    _episode_offset_rows,
    _find_episode_offset_candidate,
    is_tvdb_id,
)
from actions.manual_series_tvdb_scraper import (
    extract_tvdb_year_range,
    format_tvdb_episode_name,
    get_tvdb_cache_key,
)
from core.info_extractors import extract_episode_info


class EpisodeOffsetTests(unittest.TestCase):
    def test_tvdb_series_id_is_recognized(self):
        self.assertTrue(is_tvdb_id("tvdb12345"))
        self.assertFalse(is_tvdb_id("tt1234567"))

    def test_tvdb_episode_name_uses_existing_bracket_pattern(self):
        name = format_tvdb_episode_name(
            "Johnny Test",
            1,
            1,
            ep_title="Johnny to the Center of the Earth",
            extras="720p x264",
            ep_id="tvdb4596954",
        )
        self.assertEqual(
            name,
            "Johnny Test - S01E01 [Johnny to the Center of the Earth - 720p x264] [tvdb4596954]",
        )

    def test_tvdb_episode_name_collapses_duplicate_hyphens(self):
        name = format_tvdb_episode_name(
            "Johnny Test",
            4,
            28,
            ep_title="Who's Johnny",
            extras="- 720p x264",
            ep_id="tvdb5197789",
        )
        self.assertEqual(
            name,
            "Johnny Test - S04E28 [Who's Johnny - 720p x264] [tvdb5197789]",
        )

    def test_tvdb_episode_name_removes_title_repeated_in_extras(self):
        show, season, episode, extras = extract_episode_info(
            "American Dad! - S01E05 - Roger Codger.720p.DVDRip.x264"
        )
        name = format_tvdb_episode_name(
            show,
            season,
            episode,
            ep_title="Roger Codger",
            extras=extras,
        )

        self.assertEqual(
            name,
            "American Dad! - S01E05 [Roger Codger - 720p DVDRip x264]",
        )

    def test_tvdb_episode_name_matches_title_with_punctuation_variations(self):
        name = format_tvdb_episode_name(
            "American Dad!",
            1,
            4,
            ep_title="Francine's Flashback",
            extras="Francines Flashback 720p DVDRip x264",
        )

        self.assertEqual(
            name,
            "American Dad! - S01E04 [Francine's Flashback - 720p DVDRip x264]",
        )

    def test_tvdb_episode_name_does_not_repeat_existing_episode_id(self):
        source_name = "American Dad! - S01E01 [Pilot - 720p DVDRip x264] [tvdb108299].mkv"
        show, season, episode, extras = extract_episode_info(Path(source_name).stem)

        name = format_tvdb_episode_name(
            show,
            season,
            episode,
            ep_title="Pilot",
            extras=extras,
            ep_id="tvdb108299",
        )

        self.assertEqual(name + ".mkv", source_name)

    def test_tvdb_output_uses_sanitized_tvdb_show_title(self):
        from actions import manual_series_tvdb_scraper

        with tempfile.TemporaryDirectory() as temp_dir:
            series_dir = Path(temp_dir)
            source = series_dir / "American Dad S01E01.mkv"
            source.touch()
            metadata = {
                "show_title": "TVDB/Canonical: Show? Title (2005)",
                "year": "2005",
                "end_year": "2026",
                "tvdb_show_id": "73141",
            }

            with (
                patch.object(manual_series_tvdb_scraper, "SERIES_DIR", series_dir),
                patch.object(manual_series_tvdb_scraper, "get_tvdb_cache_key", return_value="American Dad"),
                patch.object(manual_series_tvdb_scraper, "get_tvdb_url_for_show", return_value="https://tvdb.test/series/73141"),
                patch.object(manual_series_tvdb_scraper, "fetch_tvdb_metadata", return_value=metadata),
                patch.object(manual_series_tvdb_scraper, "get_episode_from_cache", return_value={"title": "Pilot", "tvdb_id": "108299"}),
                patch.object(manual_series_tvdb_scraper, "_load_imdb_cache", return_value={}),
                patch.object(manual_series_tvdb_scraper, "_save_imdb_cache"),
            ):
                destination = manual_series_tvdb_scraper.build_to_path(source)

        expected_show = "TVDB -Canonical - Show - Title"
        self.assertEqual(
            destination.parent.parent.name,
            f"{expected_show} (2005-2026) [tvdb73141]",
        )
        self.assertTrue(destination.name.startswith(f"{expected_show} - S01E01"))

    def test_tvdb_scraper_skips_files_already_at_suggested_path(self):
        from actions import manual_series_tvdb_scraper

        with tempfile.TemporaryDirectory() as temp_dir:
            series_dir = Path(temp_dir)
            already_named = series_dir / "already-named.mkv"
            needs_rename = series_dir / "needs-rename.mkv"
            already_named.touch()
            needs_rename.touch()
            planned_file = series_dir / "planned.json"
            suggested_path = series_dir / "suggested.mkv"

            def suggested_destination(file):
                return file if file.name == already_named.name else suggested_path

            with (
                patch.object(manual_series_tvdb_scraper, "SERIES_DIR", series_dir),
                patch.object(manual_series_tvdb_scraper, "PLANNED_RENAMES_FILE", planned_file),
                patch.object(manual_series_tvdb_scraper, "is_video_file", return_value=True),
                patch.object(manual_series_tvdb_scraper, "build_to_path", side_effect=suggested_destination),
            ):
                manual_series_tvdb_scraper.main()

            with planned_file.open(encoding="utf-8") as planned_handle:
                planned = json.load(planned_handle)

        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]["from"], str(needs_rename.resolve()))
        self.assertEqual(planned[0]["to"], str(suggested_path))

    def test_tvdb_year_range_uses_first_and_recent_dates(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            """
            <li class="list-group-item">
              <strong>First Aired</strong><span>September 17, 2005</span>
              <strong>Recent</strong><span>June 18, 2014</span>
            </li>
            """,
            "html.parser",
        )
        self.assertEqual(extract_tvdb_year_range(soup), ("2005", "2014"))

    def test_tvdb_single_year_is_not_repeated(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            """
            <li class="list-group-item">
              <strong>First Aired</strong><span>January 1, 2020</span>
              <strong>Recent</strong><span>December 31, 2020</span>
            </li>
            """,
            "html.parser",
        )
        self.assertEqual(extract_tvdb_year_range(soup), ("2020", None))

    def test_tvdb_cache_key_excludes_series_root(self):
        with patch(
            "actions.manual_series_tvdb_scraper.SERIES_DIR",
            Path(r"D:\Bigger Downloads\.series\done just names"),
        ):
            direct_file = Path(r"D:\Johnny Test S01E01.mkv")
            season_file = Path(r"D:\Johnny Test\Season 01\Johnny Test S01E01.mkv")

            self.assertEqual(get_tvdb_cache_key(direct_file, "Johnny Test"), "Johnny Test")
            self.assertEqual(get_tvdb_cache_key(season_file, "Johnny Test"), "Johnny Test")

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
