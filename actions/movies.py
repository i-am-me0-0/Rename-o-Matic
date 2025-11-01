
# movies.py
# Main logic for organizing, renaming, and processing movie files in the media library.
# Handles metadata fetching, filename construction, folder organization, and user prompts for ambiguous cases.
# No threading is used in this module.

# --- Imports and Config ---
from config import MOVIES_DIR, MOVIE_FOLDER_LOCATION, CREATE_MOVIE_SUBFOLDERS, ui_debug_print
from core.file_utils import is_video_file, move_subtitles
from core.info_extractors import extract_movie_info
from undo import log_rename
import shutil
from pathlib import Path
from actions.omdb_gui_scraper import get_imdb_id_gui
from core.media_metadata_cache import get_entry, set_entry, update_entry, load_metadata
from actions.custom_imdb_web_poster_scraper import scrape_full_movie_metadata
import re
import tkinter as tk
from config import SKIP_IMDB_IDS
from core.movies_utils import clean_brackets, build_new_filename, get_destination_path, should_skip_file, get_title_diff


# def clean_brackets(text: str) -> str:
#     """Remove surrounding brackets [] or () from a string if present."""
#     if not isinstance(text, str):
#         return ""
#     text = text.strip()
#     if (text.startswith("[") and text.endswith("]")) or (text.startswith("(") and text.endswith(")")):
#         return text[1:-1].strip()
#     return text




# --- Skip Logic for IMDb IDs ---
def should_skip_due_to_imdb_id(file, imdb_id_in_name, skipped):
    """
    If a file's IMDb ID is in the skip list, fetch its metadata/posters but skip renaming/moving.
    Appends a skip message to the skipped list or prints it.
    """
    meta = get_entry(imdb_id_in_name)
    from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id, fetch_episode_ids_omdb
    if not meta:
        # Fetch metadata depending on whether it's a series or movie
        if 'S01E' in file.stem or 'season' in file.stem.lower():
            fetch_title_and_year_from_imdb_id(imdb_id_in_name)
        else:
            scrape_full_movie_metadata(imdb_id_in_name)
        meta = get_entry(imdb_id_in_name)
    if meta and meta.get('type') == 'series':
        # For series, fetch episode IDs as well
        fetch_episode_ids_omdb(imdb_id_in_name, {}, lambda: None)
    msg = f"⏭️ Skipped (IMDb ID in skip list, metadata/posters fetched): {file.name}"
    if skipped is not None:
        skipped.append(msg)
    else:
        print(msg)
    return True


# --- Metadata Cache Consistency ---
def ensure_metadata_for_cache(debug_print, get_meta_entry):
    """
    Ensure all IMDb IDs in the imdb_cache.json have corresponding metadata entries.
    Fetches missing metadata for movies and series as needed.
    """
    import json
    from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id
    try:
        with open('cache/imdb_cache.json', encoding='utf-8') as f:
            imdb_cache = json.load(f)
    except Exception:
        imdb_cache = {}
    for title, imdbid in imdb_cache.items():
        if imdbid and not get_meta_entry(imdbid):
            debug_print(f"[DEBUG] Fetching missing metadata for {title} ({imdbid}) from imdb_cache...")
            if 'S01E' in title or 'season' in title.lower():
                fetch_title_and_year_from_imdb_id(imdbid)
            else:
                scrape_full_movie_metadata(imdbid)


# --- Movie Metadata Matching and User Prompting ---
def match_movie_metadata(orig_title, orig_year, metadata, file, debug_print):
    """
    Try to match movie metadata by title and year.
    If a year mismatch is found, prompt the user to confirm, skip, or manually rescrape/select the correct IMDb entry.
    Returns a dict with imdb_id, meta, and found status.
    """
    from actions.omdb_gui_scraper import get_root
    from gui.app import AppRoot
    matched = {'imdb_id': None, 'meta': None, 'found': False, 'rescrape_later': False}
    movie_entries = [(mid, entry) for mid, entry in metadata.items() if entry.get('type') == 'movie']
    i = 0
    picker_break = False
    while i < len(movie_entries):
        mid, entry = movie_entries[i]
        i += 1
        # Check for title match
        if orig_title and entry.get('title') and entry.get('title').lower() == orig_title.lower():
            # If year matches or is not specified, accept
            if not orig_year or (entry.get('year') and entry.get('year') == orig_year):
                matched['imdb_id'] = mid
                matched['meta'] = entry
                matched['found'] = True
                debug_print(f"[DEBUG] Matched movie metadata for {orig_title} ({orig_year}) -> {mid}")
                break
            # If year mismatches, prompt user for action
            elif entry.get('year') and orig_year and entry.get('year') != orig_year:
                # Replace the old Toplevel prompt with a frame-based prompt
                from gui.year_mismatch_prompt import YearMismatchPrompt
                user_choice = {'action': None}
                app_root = get_root()
                done_var = tk.BooleanVar()

                def on_choice(action: str):
                    ui_debug_print(f"[DEBUG] YearMismatchPrompt choice={action} for {file.name}")
                    user_choice['action'] = action
                    if action == 'rescrape':
                        matched['rescrape_later'] = True
                    done_var.set(True)

                # Show the frame in the main screen container and wait
                app_root.show_screen(YearMismatchPrompt, file.name, entry, mid, on_choice)
                app_root.wait_variable(done_var)
                # Handle user choice
                if user_choice['action'] == 'no':
                    ui_debug_print(f"[DEBUG] Skipping file {file.name} after prompt.")
                    return matched
                elif user_choice['action'] == 'yes':
                    ui_debug_print(f"[DEBUG] Using existing metadata for {file.name} (ID: {mid})")
                    matched['imdb_id'] = mid
                    matched['meta'] = entry
                    matched['found'] = True
                    break
                elif user_choice['action'] == 'rescrape':
                    # Picker will be opened later in process_file
                    picker_break = True
        if picker_break:
            break
    return matched


# --- Build Extras for Filename ---
def build_extras(orig_title, meta_title, orig_year, meta_year, orig_extras):
    """
    Build an 'extras' string for the filename from any lost or differing info (title, year, extras).
    Ensures that information not present in the metadata but present in the original filename is preserved.
    """
    lost_info = []
    if orig_title and meta_title and orig_title.strip().lower() != meta_title.strip().lower():
        diff = get_title_diff(orig_title.strip(), meta_title.strip())
        if diff:
            lost_info.append(diff)
    if orig_year and meta_year and orig_year != meta_year:
        lost_info.append(orig_year)
    if orig_extras:
        lost_info.append(orig_extras)
    lost_info = [x for x in lost_info if x and x.strip() and x.strip().lower() not in (meta_title.strip().lower(), meta_year)]
    return " - ".join(lost_info) if lost_info else ""


# --- Main File Processing Logic ---
def process_file(file: Path, preview_only=False, rename_files=True, selected_files=None, planned=None, skipped=None):
    """
    Process a single movie file:
    - Extracts info from filename
    - Checks for IMDb ID in skip list
    - Ensures metadata is loaded
    - Matches or prompts for correct metadata
    - Builds new filename and destination
    - Handles renaming/moving, planning, or skipping as needed
    """
    if not file.is_file() or not is_video_file(file):
        return

    # If a selection is provided, skip files not in the selection
    if selected_files and str(file) not in selected_files:
        return

    # Extract original info from filename
    orig_title, orig_year, orig_extras = extract_movie_info(file.stem)
    imdb_id = None
    meta = None
    imdb_id_in_name = None
    m = re.search(r'(tt\d{7,8})', file.stem)
    if m:
        imdb_id_in_name = m.group(1)
    # Skip if IMDb ID is in skip list
    if imdb_id_in_name and imdb_id_in_name in SKIP_IMDB_IDS:
        if should_skip_due_to_imdb_id(file, imdb_id_in_name, skipped):
            return

    # Load all metadata
    metadata = load_metadata()
    found = False
    from config import debug_print
    from core.media_metadata_cache import get_entry as get_meta_entry
    ensure_metadata_for_cache(debug_print, get_meta_entry)

    # Try to match metadata for this file
    matched = match_movie_metadata(orig_title, orig_year, metadata, file, debug_print)
    imdb_id = matched['imdb_id']
    meta = matched['meta']
    found = matched['found']
    # If year mismatch and rescrape requested, open picker now
    if matched.get('rescrape_later'):
        ui_debug_print(f"[DBG] movies.process_file: about to call get_imdb_id_gui(rescrape) for {file.name}")
        try:
            imdb_id = get_imdb_id_gui(file.name, search_title=orig_title, force_prompt=True)
        except Exception as e:
            print(f"[ERROR] movies.process_file: get_imdb_id_gui(rescrape) raised: {e}")
            raise
        ui_debug_print(f"[DBG] movies.process_file: get_imdb_id_gui(rescrape) returned: {imdb_id}")
        if imdb_id:
            meta = get_entry(imdb_id)
            found = meta is not None
        else:
            meta = None
            found = False

    # Skip if this is a series entry (not a movie)
    for mid, entry in metadata.items():
        if entry.get('type') == 'series' and orig_title and entry.get('title') and entry.get('title').lower() == orig_title.lower():
            debug_print(f"[DEBUG] Skipping series metadata for {orig_title} (type=series, id={mid})")

    # If not found, prompt user for IMDb ID
    if not found:
        ui_debug_print(f"[DBG] movies.process_file: about to call get_imdb_id_gui for {file.name}")
        try:
            imdb_id = get_imdb_id_gui(file.name, search_title=orig_title)
        except Exception as e:
            print(f"[ERROR] movies.process_file: get_imdb_id_gui raised: {e}")
            raise
        ui_debug_print(f"[DBG] movies.process_file: get_imdb_id_gui returned: {imdb_id}")
        if imdb_id:
            meta = get_entry(imdb_id)
    # If still no metadata, skip
    if not imdb_id or not meta:
        msg = f"❌ Skipping (no metadata): {file.name}"
        if skipped is not None:
            skipped.append(msg)
        else:
            print(msg)
        return

    # Build new filename and destination path
    meta_title = meta.get('title', orig_title)
    meta_year = meta.get('year', orig_year)
    extras = build_extras(orig_title, meta_title, orig_year, meta_year, orig_extras)

    filename = build_new_filename(meta_title, meta_year, extras, imdb_id, file.suffix)
    folder_name = f"{meta_title} ({meta_year})" if CREATE_MOVIE_SUBFOLDERS else ""
    dest_folder, dest_path = get_destination_path(file, folder_name, filename, MOVIES_DIR, MOVIE_FOLDER_LOCATION, CREATE_MOVIE_SUBFOLDERS)
    def normalize_filename(name: str) -> str:
        return name.replace(" ", "").lower()

    already_named = normalize_filename(file.name) == normalize_filename(filename)
    skip_reason = should_skip_file(dest_path, file)

    # If file is already correctly named and located, skip
    if file.resolve() == dest_path.resolve():
        skip_reason = f"⏭️ Already correctly named and located: {file.name}"
        if skipped is not None:
            skipped.append(skip_reason)
        else:
            print(skip_reason)
        return

    # If only folder is wrong, move to correct folder
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

    # If should skip for other reasons, skip
    if skip_reason:
        if skipped is not None:
            skipped.append(skip_reason)
        else:
            print(skip_reason)
        return

    # If planning only, add to planned list
    if planned is not None:
        planned.append({
            "type": "Movie",
            "src": str(file),
            "dest": str(dest_path),
        })
        return

    # Print planned move/rename
    print(f"\nMovie: {file.relative_to(MOVIES_DIR.parent)}\n -> {dest_path.relative_to(MOVIES_DIR)}")

    if preview_only:
        return

    if not rename_files:
        print("📁 Folder created (no rename).")
        return

    # Actually move/rename the file and subtitles
    subs = move_subtitles(file, dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file), str(dest_path))
    log_rename(file, dest_path, subs)
    print("✅ Moved.")



# --- Simple Rename Helper ---
def rename_movie(src: Path, dest: Path):
    """
    Move a movie file and its subtitles to a new destination, logging the rename.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    subs = move_subtitles(src, dest)
    shutil.move(str(src), str(dest))
    log_rename(src, dest, subs)
    print(f"✅ Moved: {src.name}")



# --- Organize All Movies ---
def organize_movies(preview_only=False, rename_files=True, selected_files=None):
    """
    Organize all movie files in MOVIES_DIR by processing each file recursively.
    Handles KeyboardInterrupt gracefully.
    """
    try:
        for file in MOVIES_DIR.rglob("*"):
            process_file(file, preview_only, rename_files, selected_files)
    except KeyboardInterrupt:
        print("🚫 Cancelled by user.")



# --- Plan Movie Renames (Preview) ---
def plan_movie_renames():
    """
    Plan all movie renames/moves without actually performing them.
    Returns a list of planned actions and prints skipped files.
    """
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

