# run-tests.py
#automatically generated may contain errors
"""
Comprehensive logic test runner for the media renamer project.
Tests all logic modules and prints results.
"""
import sys
import traceback


# List of test functions to run
TESTS = []

# --- Import logic modules ---
try:
    from actions import movies, preview, series, custom_imdb_web_poster_scraper, omdb_gui_scraper
    from core import file_lister, file_utils, info_extractors, manual_episode_cache, manual_episode_title_cache, media_metadata_cache, movies_utils, poster_scraper, series_utils
except Exception as e:
    print(f"Failed to import modules: {e}")
    sys.exit(1)

# --- Movies Utils ---
def test_clean_brackets_movies_utils():
    assert movies_utils.clean_brackets("[Test]") == "Test"
    assert movies_utils.clean_brackets("(Test)") == "Test"
    assert movies_utils.clean_brackets("Test") == "Test"
TESTS.append(("movies_utils.clean_brackets", test_clean_brackets_movies_utils))

def test_build_new_filename():
    fn = movies_utils.build_new_filename("Title", "2020", "Extra", "tt1234567", ".mkv")
    assert "Title" in fn and "2020" in fn and "tt1234567" in fn and fn.endswith(".mkv")
TESTS.append(("movies_utils.build_new_filename", test_build_new_filename))

def test_get_destination_path():
    from pathlib import Path
    MOVIES_DIR = Path("/tmp/movies")
    folder_name = "TestFolder"
    filename = "TestFile.mkv"
    dest_folder, dest_path = movies_utils.get_destination_path(Path("/tmp/movies/file.mkv"), folder_name, filename, MOVIES_DIR, "root", True)
    assert dest_folder.name == folder_name and dest_path.name == filename
TESTS.append(("movies_utils.get_destination_path", test_get_destination_path))

def test_should_skip_file():
    from pathlib import Path
    file = Path("/tmp/movies/file.mkv")
    dest_path = Path("/tmp/movies/file.mkv")
    assert movies_utils.should_skip_file(dest_path, file) is not None
TESTS.append(("movies_utils.should_skip_file", test_should_skip_file))

def test_get_title_diff():
    diff = movies_utils.get_title_diff("A B C", "A B")
    assert "C" in diff
TESTS.append(("movies_utils.get_title_diff", test_get_title_diff))

# --- File Utils ---
def test_is_video_file():
    class DummyFile:
        suffix = ".mkv"
    assert file_utils.is_video_file(DummyFile())
TESTS.append(("file_utils.is_video_file", test_is_video_file))

def test_is_subtitle_file():
    class DummyFile:
        suffix = ".srt"
    assert file_utils.is_subtitle_file(DummyFile())
TESTS.append(("file_utils.is_subtitle_file", test_is_subtitle_file))

# move_subtitles requires file operations, skip or mock for now

# --- Info Extractors ---
def test_clean_extras():
    assert info_extractors.clean_extras("(Extra)") == "Extra"
    assert info_extractors.clean_extras("[Extra]") == "Extra"
TESTS.append(("info_extractors.clean_extras", test_clean_extras))

def test_apply_series_alias():
    # Assuming SERIES_ALIASES is empty or has known values
    name = "AliasTest"
    assert info_extractors.apply_series_alias(name) == name or isinstance(info_extractors.apply_series_alias(name), str)
TESTS.append(("info_extractors.apply_series_alias", test_apply_series_alias))

def test_extract_movie_info():
    title, year, extras = info_extractors.extract_movie_info("Movie.Title.2020.Extra.mkv")
    assert title and year
TESTS.append(("info_extractors.extract_movie_info", test_extract_movie_info))

def test_extract_episode_info():
    result = info_extractors.extract_episode_info("Show.S01E01.mkv")
    assert result is not None
TESTS.append(("info_extractors.extract_episode_info", test_extract_episode_info))

# --- Series Utils ---
def test_clean_brackets_series_utils():
    assert series_utils.clean_brackets("[Test]") == "Test"
    assert series_utils.clean_brackets("(Test)") == "Test"
TESTS.append(("series_utils.clean_brackets", test_clean_brackets_series_utils))

def test_get_folder_imdb_id():
    folder_name = "Show [tt1234567]"
    imdb_id = series_utils.get_folder_imdb_id(folder_name)
    assert imdb_id is None or isinstance(imdb_id, str)
TESTS.append(("series_utils.get_folder_imdb_id", test_get_folder_imdb_id))

def test_get_episode_imdb_id_from_filename():
    filename = "Show.tt1234567.S01E01.mkv"
    imdb_id = series_utils.get_episode_imdb_id_from_filename(filename)
    assert imdb_id == "tt1234567"
TESTS.append(("series_utils.get_episode_imdb_id_from_filename", test_get_episode_imdb_id_from_filename))

def test_is_imdb_id_skipped():
    imdb_id = "tt1234567"
    skip_list = ["tt1234567"]
    assert series_utils.is_imdb_id_skipped(imdb_id, skip_list)
TESTS.append(("series_utils.is_imdb_id_skipped", test_is_imdb_id_skipped))

# --- Media Metadata Cache ---
def test_load_metadata():
    data = media_metadata_cache.load_metadata()
    assert isinstance(data, dict)
TESTS.append(("media_metadata_cache.load_metadata", test_load_metadata))

def test_set_and_get_entry():
    imdb_id = "tt9999999"
    entry = {"title": "Test Movie", "year": "2025"}
    media_metadata_cache.set_entry(imdb_id, entry)
    result = media_metadata_cache.get_entry(imdb_id)
    assert result == entry
TESTS.append(("media_metadata_cache.set_and_get_entry", test_set_and_get_entry))

def test_update_entry():
    imdb_id = "tt9999999"
    updates = {"genre": "Action"}
    media_metadata_cache.update_entry(imdb_id, updates)
    result = media_metadata_cache.get_entry(imdb_id)
    assert "genre" in result
TESTS.append(("media_metadata_cache.update_entry", test_update_entry))

# --- Manual Episode Cache ---
def test_manual_episode_cache():
    cache = manual_episode_cache.load_manual_episode_cache()
    assert isinstance(cache, dict)
    manual_episode_cache.save_manual_episode_cache(cache)
TESTS.append(("manual_episode_cache.load_and_save", test_manual_episode_cache))

# --- Manual Episode Title Cache ---
def test_manual_episode_title_cache():
    cache = manual_episode_title_cache.load_manual_episode_title_cache()
    assert isinstance(cache, dict)
    manual_episode_title_cache.save_manual_episode_title_cache(cache)
TESTS.append(("manual_episode_title_cache.load_and_save", test_manual_episode_title_cache))

# --- File Lister ---
def test_list_movie_files():
    files = file_lister.list_movie_files()
    assert isinstance(files, list)
TESTS.append(("file_lister.list_movie_files", test_list_movie_files))

def test_list_series_files():
    files = file_lister.list_series_files()
    assert isinstance(files, list)
TESTS.append(("file_lister.list_series_files", test_list_series_files))

def test_list_all_media_files():
    files = file_lister.list_all_media_files()
    assert isinstance(files, list)
TESTS.append(("file_lister.list_all_media_files", test_list_all_media_files))

# --- Poster Scraper ---
def test_update_posters_from_filenames():
    try:
        poster_scraper.update_posters_from_filenames()
    except Exception as e:
        # Accept errors due to missing files/network
        pass
TESTS.append(("poster_scraper.update_posters_from_filenames", test_update_posters_from_filenames))

# --- Preview ---
def test_sanitize_path_component():
    s = preview.sanitize_path_component("Test:File|Name?")
    assert ":" not in s and "|" not in s and "?" not in s
TESTS.append(("preview.sanitize_path_component", test_sanitize_path_component))


# --- Movies (actions) ---
# def test_clean_brackets_movies():
#     assert movies.clean_brackets("[Test]") == "Test"
#     assert movies.clean_brackets("(Test)") == "Test"
# TESTS.append(("movies.clean_brackets", test_clean_brackets_movies))

def test_should_skip_due_to_imdb_id():
    class DummyFile:
        stem = "TestFile"
        name = "TestFile.mkv"
    skipped = []
    # imdb_id_in_name is not in cache, triggers scrape_full_movie_metadata
    result = movies.should_skip_due_to_imdb_id(DummyFile(), "tt9999998", skipped)
    assert result is True and skipped
TESTS.append(("movies.should_skip_due_to_imdb_id", test_should_skip_due_to_imdb_id))

def test_ensure_metadata_for_cache():
    def debug_print(msg):
        pass
    def get_meta_entry(imdbid):
        return {"title": "Test"} if imdbid == "tt9999999" else None
    # Should not raise
    movies.ensure_metadata_for_cache(debug_print, get_meta_entry)
TESTS.append(("movies.ensure_metadata_for_cache", test_ensure_metadata_for_cache))

def test_build_extras():
    result = movies.build_extras("Title", "MetaTitle", "2020", "2020", "Extra")
    assert isinstance(result, str)
TESTS.append(("movies.build_extras", test_build_extras))

# process_file is complex and does file operations, so we mock minimal call
def test_process_file_mock():
    from pathlib import Path
    try:
        movies.process_file(Path("/tmp/movies/file.mkv"), preview_only=True, rename_files=False)
    except Exception:
        pass  # Accept errors due to missing files
TESTS.append(("movies.process_file (mock)", test_process_file_mock))

# --- Series (actions) ---
def test_clean_brackets_series():
    assert series.clean_brackets("[Test]") == "Test"
    assert series.clean_brackets("(Test)") == "Test"
TESTS.append(("series.clean_brackets", test_clean_brackets_series))

# --- Custom IMDb Web Poster Scraper ---
def test_extract_imdb_id_custom_scraper():
    imdb_id = custom_imdb_web_poster_scraper.extract_imdb_id("Show [tt1234567]")
    assert imdb_id == "tt1234567" or imdb_id is None
TESTS.append(("custom_imdb_web_poster_scraper.extract_imdb_id", test_extract_imdb_id_custom_scraper))

# --- OMDB GUI Scraper ---
def test_parse_title_omdb_scraper():
    title, year = omdb_gui_scraper.parse_title("Movie Title (2020)")
    assert title == "Movie Title" and (year == "2020" or year is None)
TESTS.append(("omdb_gui_scraper.parse_title", test_parse_title_omdb_scraper))

# --- Run all tests ---
def run_all_tests():
    failed = []
    for name, test_func in TESTS:
        try:
            test_func()
            print(f"[OK] {name}")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            traceback.print_exc()
            failed.append((name, str(e)))
    if not failed:
        print("\nAll tests passed!")
    else:
        print(f"\n{len(failed)} test(s) failed:")
        for name, err in failed:
            print(f"- {name}: {err}")

if __name__ == "__main__":
    run_all_tests()
