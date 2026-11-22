import unittest

from core.info_extractors import extract_episode_info, extract_movie_info
from core.movies_utils import get_title_diff


class MovieTitleDifferenceTests(unittest.TestCase):
    def test_ignores_accents_and_word_reordering(self):
        diff = get_title_diff(
            "Pokemon - 003 - The Movie 3",
            "Pokémon 3 the Movie - Spell of the Unown",
        )

        self.assertEqual(diff, "003")

    def test_preserves_collection_number_when_title_word_is_reordered(self):
        diff = get_title_diff(
            "Pokemon - 004 - 4Ever",
            "Pokemon 4Ever - Celebi - Voice of the Forest",
        )

        self.assertEqual(diff, "004")


class ExtractMovieInfoFallbackTests(unittest.TestCase):
    def test_preserves_numbered_title_without_year(self):
        result = extract_movie_info("Pokemon  - 003 - The Movie 3 720p HEVC")

        self.assertEqual(
            result,
            ("Pokemon  - 003 - The Movie 3", None, "720p HEVC"),
        )


class ExtractEpisodeInfoFallbackTests(unittest.TestCase):
    def test_uses_folder_name_when_filename_has_no_show(self):
        show, season, episode, extras = extract_episode_info("S01E02 [720p]", folder_name="The Office")

        self.assertEqual(show, "The Office")
        self.assertEqual(season, 1)
        self.assertEqual(episode, 2)
        self.assertEqual(extras, "720p")

    def test_uses_folder_name_for_filename_starting_with_season_episode(self):
        show, season, episode, extras = extract_episode_info(
            "s01e01_Welcome.to.LazyTown 720p x265",
            folder_name="LazyTown.2004-2014.web",
        )

        self.assertEqual(show, "LazyTown 2004-2014 web")
        self.assertEqual(season, 1)
        self.assertEqual(episode, 1)


if __name__ == "__main__":
    unittest.main()
