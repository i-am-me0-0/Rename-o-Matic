# # Blank slate planned renames generator for series
# import json
# from pathlib import Path
# from config import SERIES_DIR, PLANNED_RENAMES_FILE
# from core.file_utils import is_video_file

# def main():
# 	planned = []
# 	# Recursively list all video files in SERIES_DIR
# 	for file in Path(SERIES_DIR).rglob("*"):
# 		if file.is_file() and is_video_file(file):
# 			planned.append({
# 				"include": 1,
# 				"type": "Series",
# 				"from": str(file.resolve()),
# 				"to": str(file.resolve())
				
# 			})
# 	with open(PLANNED_RENAMES_FILE, "w", encoding="utf-8") as f:
# 		json.dump(planned, f, indent=2, ensure_ascii=False)
# 	print(f"Planned renames written to {PLANNED_RENAMES_FILE} (blank slate, ready for manual editing)")

# if __name__ == "__main__":
# 	main()






# Blank slate planned renames generator for series
#
# Parses each filename with the existing pattern-matching logic
# (core.info_extractors.extract_episode_info) to guess show/season/episode/extras,
# then builds a "to" path using the SAME naming conventions as
# core.series.build_episode_path (Show (Year) [ttID]/Season SS/Show - SxxEyy [extras].ext)
# -- but WITHOUT touching any cache or OMDb lookup:
#   - no core.media_metadata_cache (get_entry/load_metadata/etc.)
#   - no actions.omdb_gui_scraper (fetch_title_and_year_from_imdb_id, fetch_episode_ids_omdb)
#   - no core.manual_episode_cache / core.manual_episode_title_cache
#   - no imdb_cache.json reads (that's what get_folder_imdb_id falls back to, so we
#     don't call it -- we only regex the folder/show text directly for an embedded id)
#
# If a year or IMDb id is genuinely embedded in the filename/folder text, we use it.
# Otherwise we leave literal YEAR / ttXXXXXXX placeholders for the user to fill in
# by hand when reviewing planned_renames.json.

import json
import re
from pathlib import Path
from config import SERIES_DIR, PLANNED_RENAMES_FILE
from core.file_utils import is_video_file
from core.info_extractors import extract_episode_info

YEAR_PLACEHOLDER = "YEAR"
IMDB_PLACEHOLDER = "ttXXXXXXX"

IMDB_ID_RE = re.compile(r'(tt\d{7,8})')
# Matches "(2007)" or "(1982-1986)" / "(1982–1986)" embedded in a title
EMBEDDED_YEAR_RE = re.compile(r'\s*\((\d{4})(?:\s*[-\u2013\u2014]\s*(\d{4}))?\)\s*')


def build_episode_suffix(episode):
    """Turn the episode value from extract_episode_info into an ExxEyy style string."""
    if isinstance(episode, (list, tuple)):
        nums = [int(e) for e in episode if str(e).isdigit()]
        if not nums:
            return "E00"
        return "E" + "E".join(f"{n:02}" for n in nums)
    if episode is not None:
        return f"E{int(episode):02}"
    return "E00"


def extract_embedded_year(show_text: str):
    """Pull a "(YYYY)" or "(YYYY-YYYY)" out of a parsed show name, if present.

    extract_episode_info() only strips the S/E token out of the raw text -- it
    does NOT strip a year that happens to sit in the title (e.g. filenames like
    "Phineas and Ferb (2007) - S00E02 - ..." parse show as "Phineas and Ferb (2007)").
    Returns (show_without_year, year_str_or_None).
    """
    m = EMBEDDED_YEAR_RE.search(show_text)
    if not m:
        return show_text.strip(), None
    start, end = m.group(1), m.group(2)
    year_str = f"{start}-{end}" if end and end != start else start
    cleaned = (show_text[:m.start()] + " " + show_text[m.end():]).strip()
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(" -")
    return cleaned, year_str


def extract_embedded_imdb_id(text: str):
    """Regex-only lookup of a tt-id already sitting in the text (filename/folder).

    This is NOT the imdb_cache.json fallback that get_folder_imdb_id() uses --
    just a direct regex match on text we already have in hand.
    """
    if not text:
        return None
    m = IMDB_ID_RE.search(text)
    return m.group(1) if m else None


def build_to_path(file: Path):
    ext = file.suffix
    show_raw, season, episode, extras = extract_episode_info(file.stem)

    show_raw = (show_raw or "UNKNOWN_SHOW").strip()
    season = season if season is not None else 1

    # Strip an embedded year out of the parsed show name so we don't end up
    # with "Show (2007) (YEAR)" -- use the embedded year if we found one.
    show, embedded_year = extract_embedded_year(show_raw)
    year_str = embedded_year or YEAR_PLACEHOLDER

    # Prefer an IMDb id already embedded in the show text or the parent folder
    # name over the placeholder -- but never fall back to any on-disk cache.
    imdb_id = (
        extract_embedded_imdb_id(show_raw)
        or extract_embedded_imdb_id(file.parent.name)
        or IMDB_PLACEHOLDER
    )

    season_str = f"S{season:02}"
    ep_str = build_episode_suffix(episode)

    show_folder = f"{show} ({year_str}) [{imdb_id}]"
    season_folder = f"Season {season:02}"

    episode_filename = f"{show} - {season_str}{ep_str}"
    if extras:
        episode_filename += f" [{extras}]"
    episode_filename += ext

    return Path(SERIES_DIR) / show_folder / season_folder / episode_filename


def main():
    planned = []
    # Recursively list all video files in SERIES_DIR
    for file in Path(SERIES_DIR).rglob("*"):
        if file.is_file() and is_video_file(file):
            to_path = build_to_path(file)
            planned.append({
                "include": 1,
                "type": "Series",
                "from": str(file.resolve()),
                "to": str(to_path)
            })

    with open(PLANNED_RENAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(planned, f, indent=2, ensure_ascii=False)
    print(f"Planned renames written to {PLANNED_RENAMES_FILE} "
          f"(filenames parsed, {YEAR_PLACEHOLDER}/{IMDB_PLACEHOLDER} left for manual editing where not found)")


if __name__ == "__main__":
    main()

