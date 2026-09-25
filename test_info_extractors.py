import unittest

from core.info_extractors import extract_episode_info


class ExtractEpisodeInfoFallbackTests(unittest.TestCase):
    def test_uses_folder_name_when_filename_has_no_show(self):
        show, season, episode, extras = extract_episode_info("S01E02 [720p]", folder_name="The Office")

        self.assertEqual(show, "The Office")
        self.assertEqual(season, 1)
        self.assertEqual(episode, 2)
        self.assertEqual(extras, "720p")


if __name__ == "__main__":
    unittest.main()
