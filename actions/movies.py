#movies.py

#no threading
from config import MOVIES_DIR, MOVIE_FOLDER_LOCATION, CREATE_MOVIE_SUBFOLDERS
from core.file_utils import is_video_file, move_subtitles
from core.info_extractors import extract_movie_info
from undo import log_rename
import shutil
from pathlib import Path
from actions.omdb_gui_scraper import get_imdb_id_gui
from core.media_metadata_cache import get_entry, set_entry, update_entry, load_metadata
from actions.custom_imdb_web_poster_scraper import scrape_full_movie_metadata
import re
from config import SKIP_IMDB_IDS
from core.movies_utils import clean_brackets, build_new_filename, get_destination_path, should_skip_file, get_title_diff


def clean_brackets(text: str) -> str:
    """Remove surrounding brackets [] or () from a string if present."""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if (text.startswith("[") and text.endswith("]")) or (text.startswith("(") and text.endswith(")")):
        return text[1:-1].strip()
    return text


def process_file(file: Path, preview_only=False, rename_files=True, selected_files=None, planned=None, skipped=None):
    if not file.is_file() or not is_video_file(file):
        return

    if selected_files and str(file) not in selected_files:
        return

    # Extract info from filename
    
    orig_title, orig_year, orig_extras = extract_movie_info(file.stem)
    imdb_id = None
    meta = None
    # Check for IMDb ID in filename and skip renaming if in skip list, but fetch metadata/posters
    imdb_id_in_name = None
    m = re.search(r'(tt\d{7,8})', file.stem)
    if m:
        imdb_id_in_name = m.group(1)
    if imdb_id_in_name and imdb_id_in_name in SKIP_IMDB_IDS:
        # Fetch metadata/posters/episode ids as usual
        meta = get_entry(imdb_id_in_name)
        from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id, fetch_episode_ids_omdb
        # Guess type: if S01E or 'season' in filename, treat as series, else movie
        if not meta:
            if 'S01E' in file.stem or 'season' in file.stem.lower():
                fetch_title_and_year_from_imdb_id(imdb_id_in_name)
            else:
                scrape_full_movie_metadata(imdb_id_in_name)
            meta = get_entry(imdb_id_in_name)
        # For series, try to fetch episode ids
        if meta and meta.get('type') == 'series':
            fetch_episode_ids_omdb(imdb_id_in_name, {}, lambda: None)
        msg = f"⏭️ Skipped (IMDb ID in skip list, metadata/posters fetched): {file.name}"
        if skipped is not None:
            skipped.append(msg)
        else:
            print(msg)
        return
    # Try to get imdb_id from filename (if present in extras)
    # Otherwise, search metadata for matching title/year
    # (Assume get_imdb_id_gui is now only used for missing metadata, not for year prompt)
    # 1. Try to find by title/year in metadata
    metadata = load_metadata()
    found = False
    # --- NEW: Ensure all imdb_ids in imdb_cache have metadata, and never overwrite movie/series types ---
    from config import debug_print
    from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id
    from core.media_metadata_cache import get_entry as get_meta_entry
    import json
    try:
        with open('cache/imdb_cache.json', encoding='utf-8') as f:
            imdb_cache = json.load(f)
    except Exception:
        imdb_cache = {}
    # For each imdb_id in imdb_cache, if not in metadata, fetch and add
    for title, imdbid in imdb_cache.items():
        if imdbid and not get_meta_entry(imdbid):
            debug_print(f"[DEBUG] Fetching missing metadata for {title} ({imdbid}) from imdb_cache...")
            # Try to guess type: if S01E or 'season' in title, treat as series, else movie
            if 'S01E' in title or 'season' in title.lower():
                fetch_title_and_year_from_imdb_id(imdbid)
            else:
                scrape_full_movie_metadata(imdbid)
    # Now, do not overwrite movie/series metadata with the other type
    # Only consider movie entries for matching
    movie_entries = [(mid, entry) for mid, entry in metadata.items() if entry.get('type') == 'movie']
    for mid, entry in movie_entries:
        if orig_title and entry.get('title') and entry.get('title').lower() == orig_title.lower():
            if not orig_year or (entry.get('year') and entry.get('year') == orig_year):
                imdb_id = mid
                meta = entry
                found = True
                debug_print(f"[DEBUG] Matched movie metadata for {orig_title} ({orig_year}) -> {mid}")
                break
    # Optionally, print debug info for skipped series with matching title
    for mid, entry in metadata.items():
        if entry.get('type') == 'series' and orig_title and entry.get('title') and entry.get('title').lower() == orig_title.lower():
            debug_print(f"[DEBUG] Skipping series metadata for {orig_title} (type=series, id={mid})")
    # 2. If not found, try to fetch via GUI (user search)
    if not found:
        imdb_id = get_imdb_id_gui(file.name, search_title=orig_title)
        if imdb_id:
            meta = get_entry(imdb_id)
    if not imdb_id or not meta:
        msg = f"❌ Skipping (no metadata): {file.name}"
        if skipped is not None:
            skipped.append(msg)
        else:
            print(msg)
        return

    # Use metadata for title/year
    meta_title = meta.get('title', orig_title)
    meta_year = meta.get('year', orig_year)

    # Build extras: append only info lost from original filename (not in metadata)
    lost_info = []
    # If the original title differs from metadata, add only the difference to extras
    if orig_title and meta_title and orig_title.strip().lower() != meta_title.strip().lower():
        diff = get_title_diff(orig_title.strip(), meta_title.strip())
        if diff:
            lost_info.append(diff)
    # If the original year differs from metadata, add to extras
    if orig_year and meta_year and orig_year != meta_year:
        lost_info.append(orig_year)
    # If there were extras in the original filename, add them
    if orig_extras:
        lost_info.append(orig_extras)
    # Remove duplicates and empty
    lost_info = [x for x in lost_info if x and x.strip() and x.strip().lower() not in (meta_title.strip().lower(), meta_year)]
    extras = " - ".join(lost_info) if lost_info else ""

    # Build new filename using metadata
    filename = build_new_filename(meta_title, meta_year, extras, imdb_id, file.suffix)
    folder_name = f"{meta_title} ({meta_year})" if CREATE_MOVIE_SUBFOLDERS else ""
    dest_folder, dest_path = get_destination_path(file, folder_name, filename, MOVIES_DIR, MOVIE_FOLDER_LOCATION, CREATE_MOVIE_SUBFOLDERS)
    def normalize_filename(name: str) -> str:
        return name.replace(" ", "").lower()

    already_named = normalize_filename(file.name) == normalize_filename(filename)
    skip_reason = should_skip_file(dest_path, file)

    if file.resolve() == dest_path.resolve():
        skip_reason = f"⏭️ Already correctly named and located: {file.name}"
        if skipped is not None:
            skipped.append(skip_reason)
        else:
            print(skip_reason)
        return

    if already_named:
        if planned is not None:
            planned.append({
                "type": "Movie",
                "src": str(file),
                "dest": str(dest_path),
            })
            return
        print(f"\n📁 Moving to correct folder: {file.relative_to(MOVIES_DIR.parent)} -> {dest_path.relative_to(MOVIES_DIR)}")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file), str(dest_path))
        log_rename(file, dest_path, move_subtitles(file, dest_path))
        print("✅ Moved (folder fix).")
        return

    if skip_reason:
        if skipped is not None:
            skipped.append(skip_reason)
        else:
            print(skip_reason)
        return

    if planned is not None:
        planned.append({
            "type": "Movie",
            "src": str(file),
            "dest": str(dest_path),
        })
        return

    print(f"\nMovie: {file.relative_to(MOVIES_DIR.parent)}\n -> {dest_path.relative_to(MOVIES_DIR)}")

    if preview_only:
        return

    if not rename_files:
        print("📁 Folder created (no rename).")
        return

    subs = move_subtitles(file, dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file), str(dest_path))
    log_rename(file, dest_path, subs)
    print("✅ Moved.")


def rename_movie(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    subs = move_subtitles(src, dest)
    shutil.move(str(src), str(dest))
    log_rename(src, dest, subs)
    print(f"✅ Moved: {src.name}")


def organize_movies(preview_only=False, rename_files=True, selected_files=None):
    try:
        for file in MOVIES_DIR.rglob("*"):
            process_file(file, preview_only, rename_files, selected_files)
    except KeyboardInterrupt:
        print("🚫 Cancelled by user.")


def plan_movie_renames():
    planned = []
    skipped = []
    try:
        for file in MOVIES_DIR.rglob("*"):
            process_file(file, planned=planned, skipped=skipped)
    except KeyboardInterrupt:
        print("🚫 Cancelled by user.")
    for msg in skipped:
        print(msg)
    return planned

