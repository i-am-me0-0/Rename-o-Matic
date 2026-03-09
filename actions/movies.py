
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
        # Fetch metadata via OMDb first (safer canonical typing); populate episodes if it looks like a series
        try:
            fetch_title_and_year_from_imdb_id(imdb_id_in_name, populate_episodes=True, fetch_poster=False)
        except Exception:
            # Fallback to the HTML scraper if OMDb fails
            try:
                scrape_full_movie_metadata(imdb_id_in_name)
            except Exception:
                pass
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
        if not imdbid:
            continue
        meta_now = get_meta_entry(imdbid)
        # Fetch if metadata missing entirely, or title/year missing
        if not meta_now or not meta_now.get('title') or not meta_now.get('year'):
            debug_print(f"[DEBUG] Fetching missing metadata for {title} ({imdbid}) from imdb_cache...")
            # Use OMDb-based fetch which correctly reports type (movie/series) and totalSeasons.
            # The previous heuristic (looking for 'S01E' or 'season' in the title) misclassified
            # folder-based keys like 'Ducktales 2017' as movies and caused scraper to write
            # movie-only metadata. Always use OMDb first to get canonical type/year information.
            try:
                # Fetch show/movie metadata via OMDb. Populate episodes and avoid extra poster scraping
                fetch_title_and_year_from_imdb_id(imdbid, populate_episodes=True, fetch_poster=False)
                # fetch_title_and_year_from_imdb_id will persist totalSeasons and episodes when appropriate
            except Exception:
                # Fallback to the HTML scraper if OMDb fails
                try:
                    scrape_full_movie_metadata(imdbid)
                except Exception:
                    pass
            


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
                # use string-typed default to avoid static-type issues when assigning
                user_choice = {'action': ''}
                app_root = get_root()
                done_var = tk.BooleanVar()

                def on_choice(action: str):
                    ui_debug_print(f"[DEBUG] YearMismatchPrompt choice={action} (type={type(action)}) for {file.name}")
                    user_choice['action'] = action
                    if action == 'rescrape':
                        matched['rescrape_later'] = True
                    elif action == 'use_cache':
                        ui_debug_print(f"[DEBUG] Opening cache picker for {file.name}")
                        try:
                            from gui.existing_cache_picker import ExistingCachePickerFrame
                            app_root = get_root()
                            picker_done = tk.BooleanVar()
                            selected_id = {'imdb_id': None}
                            def picker_callback(imdb_id):
                                ui_debug_print(f"[DEBUG] Cache picker returned imdb_id={imdb_id} (type={type(imdb_id)}) for {file.name}")
                                selected_id['imdb_id'] = imdb_id
                                picker_done.set(True)
                            filter_type = entry.get('type') if entry and 'type' in entry else None
                            top = tk.Toplevel(app_root)
                            top.title("Pick Existing Cache Entry")
                            top.geometry("650x530+200+200")
                            frame = ExistingCachePickerFrame(top, file.name, mid or '', picker_callback, filter_type=filter_type)
                            frame.pack(fill='both', expand=True)
                            top.transient(app_root.winfo_toplevel())
                            top.grab_set()
                            app_root.wait_variable(picker_done)
                            try:
                                top.destroy()
                            except Exception:
                                pass
                            imdb_id_selected = selected_id['imdb_id']
                            ui_debug_print(f"[DEBUG] Picker done, imdb_id_selected={imdb_id_selected} (type={type(imdb_id_selected)}) for {file.name}")
                            
                            # Handle special signals from cache picker
                            if imdb_id_selected == "__RESCRAPE__":
                                ui_debug_print(f"[DEBUG] Cache picker signaled rescrape for {file.name}")
                                matched['rescrape_later'] = True
                            elif imdb_id_selected:
                                from core.media_metadata_cache import get_entry as _get_entry
                                meta = _get_entry(imdb_id_selected)
                                ui_debug_print(f"[DEBUG] Metadata fetched for imdb_id_selected: {meta}")
                                if meta:
                                    matched['imdb_id'] = imdb_id_selected
                                    matched['meta'] = meta
                                    matched['found'] = True
                            # If None, user went back - do nothing, year mismatch prompt stays open
                        except Exception as e:
                            ui_debug_print(f"[DEBUG] Failed to fetch metadata for use_cache: {e}")
                    elif isinstance(action, str) and action.startswith('tt'):
                        ui_debug_print(f"[DEBUG] Handling imdb id string action: {action}")
                        try:
                            from core.media_metadata_cache import get_entry as _get_entry
                            meta = _get_entry(action)
                            ui_debug_print(f"[DEBUG] Metadata fetched for imdb id string: {meta}")
                            if meta:
                                matched['imdb_id'] = action
                                matched['meta'] = meta
                                matched['found'] = True
                        except Exception as e:
                            ui_debug_print(f"[DEBUG] Failed to fetch metadata for imdb id {action}: {e}")
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
    
    # Sanity: If we somehow have an imdb_id but meta is missing or not a dict, try to resolve it
    try:
        imdb_id_to_check = matched.get('imdb_id')
        if imdb_id_to_check and not isinstance(matched.get('meta'), dict):
            ui_debug_print(f"[SANITY] match_movie_metadata: imdb_id present but meta missing/invalid for file {file.name}: imdb_id={imdb_id_to_check}, meta={matched.get('meta')}")
            try:
                from core.media_metadata_cache import get_entry as _get_entry
                fetched = _get_entry(imdb_id_to_check)
                ui_debug_print(f"[SANITY] match_movie_metadata: fetched meta type={type(fetched)} value={fetched}")
                if isinstance(fetched, dict):
                    matched['meta'] = fetched
                    matched['found'] = True
            except Exception as e:
                ui_debug_print(f"[SANITY] match_movie_metadata: failed to fetch meta for {imdb_id_to_check}: {e}")
    except Exception:
        pass
    
    return matched


# --- Build Extras for Filename ---
def build_extras(orig_title, meta_title, orig_year, meta_year, orig_extras, old_imdb_id=None, new_imdb_id=None):
    """
    Build an 'extras' string for the filename from any lost or differing info (title, year, extras).
    Ensures that information not present in the metadata but present in the original filename is preserved.
    If old_imdb_id differs from new_imdb_id, the old one is preserved in extras.
    """
    import unicodedata
    
    lost_info = []
    
    # Normalize titles to check for real differences (ignoring punctuation/spacing)
    def _normalize_for_comparison(title):
        if not title:
            return ""
        title = unicodedata.normalize("NFKD", str(title))
        # map dash variants to ASCII hyphen
        title = re.sub(r"[‐-‒–—―]", "-", title)
        title = title.replace("&", "and")
        # replace dots with spaces for acronyms (E.T. -> E T)
        title = re.sub(r"\.", " ", title)
        # remove ! and ?
        title = title.replace("!", "").replace("?", "")
        # remove punctuation but keep spaces and hyphens
        title = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
        # replace hyphens with spaces so "Extra-Terrestrial" and "Extra Terrestrial" match
        title = title.replace("-", " ")
        # collapse multiple spaces
        title = re.sub(r"\s+", " ", title).strip().lower()
        return title
    
    # Check for title difference (ignoring punctuation)
    if orig_title and meta_title:
        norm_orig = _normalize_for_comparison(orig_title)
        norm_meta = _normalize_for_comparison(meta_title)
        
        # Only call get_title_diff if normalized forms are actually different
        if norm_orig != norm_meta:
            diff = get_title_diff(orig_title.strip(), meta_title.strip())
            if diff and diff.strip():
                # Filter out 4-digit years from diff (titles like "2001")
                diff_cleaned = ' '.join([w for w in diff.split() if not re.match(r'^\d{4}$', w)])
                if diff_cleaned.strip():
                    lost_info.append(diff_cleaned.strip())
    
    # Add year if different
    if orig_year and meta_year and orig_year != meta_year:
        lost_info.append(orig_year)
    
    # Clean and add orig_extras
    if orig_extras:
        cleaned = orig_extras
        # Only remove the NEW IMDb ID (the correct one that will be appended)
        if new_imdb_id:
            cleaned = re.sub(r'\[?' + re.escape(new_imdb_id) + r'\]?', '', cleaned)
        # Remove all brackets
        cleaned = re.sub(r'[\[\]()]', '', cleaned)
        # Remove meta_year if present
        if meta_year:
            cleaned = re.sub(r'\b' + str(meta_year) + r'\b', '', cleaned)
        # Clean up multiple spaces and dashes
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip(' -')
        
        if cleaned:
            lost_info.append(cleaned)
    
    # Filter empty items
    lost_info = [x.strip() for x in lost_info if x and x.strip()]
    
    # Build result
    result = " - ".join(lost_info) if lost_info else ""
    
    # Final cleanup of separators
    result = result.strip()
    result = re.sub(r'^[\s\-]+', '', result)  # Remove leading dashes/spaces
    result = re.sub(r'[\s\-]+$', '', result)  # Remove trailing dashes/spaces
    
    return result


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

    # If the filename contains an IMDb id but it's not yet present in the media
    # metadata cache, attempt to fetch metadata now (prefer OMDb, fallback to
    # the HTML scraper). This ensures files that already contain an imdb id can
    # be processed immediately instead of being skipped due to missing cache.
    if imdb_id_in_name:
        try:
            meta_now = get_entry(imdb_id_in_name)
        except Exception:
            meta_now = None
        if not meta_now:
            try:
                # Local import to avoid cycles and keep UI-free call-paths safe
                from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id, scrape_full_movie_metadata
                try:
                    # Try OMDb first; populate episodes if it's a series
                    fetch_title_and_year_from_imdb_id(imdb_id_in_name, populate_episodes=True, fetch_poster=False)
                except Exception:
                    # Fallback to HTML scraper if OMDb fails
                    try:
                        scrape_full_movie_metadata(imdb_id_in_name)
                    except Exception:
                        pass
                # Re-read from cache after attempted fetch
                try:
                    meta_now = get_entry(imdb_id_in_name)
                except Exception:
                    meta_now = None
            except Exception:
                meta_now = None
        # If we fetched metadata, ensure poster_url is populated too (use custom scraper)
        if meta_now and isinstance(meta_now, dict):
            try:
                # Only fetch poster if not present
                if not meta_now.get('poster_url'):
                    from actions.custom_imdb_web_poster_scraper import fetch_poster_url_and_store
                    try:
                        fetch_poster_url_and_store(imdb_id_in_name)
                    except Exception:
                        pass
            except Exception:
                pass
        # If we now have metadata, use it to set imdb_id/meta/found as appropriate
        if meta_now and isinstance(meta_now, dict):
            imdb_id = imdb_id_in_name
            meta = meta_now
            found = True

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
            # Try extracting IMDb id from filename/folders first before prompting
            m = re.search(r"(tt\d{6,9})", file.stem)
            if not m:
                p = file.parent
                depth = 0
                while p and depth < 3:
                    mm = re.search(r"(tt\d{6,9})", p.name)
                    if mm:
                        m = mm
                        break
                    p = p.parent
                    depth += 1
            if m:
                imdb_id = m.group(1)
                ui_debug_print(f"[DBG] movies.process_file: extracted imdb id {imdb_id} from path for rescrape {file.name}")
            else:
                imdb_id = get_imdb_id_gui(file.name, search_title=orig_title, force_prompt=True)
        except Exception as e:
            print(f"[ERROR] movies.process_file: get_imdb_id_gui(rescrape) raised: {e}")
            raise
        ui_debug_print(f"[DBG] movies.process_file: get_imdb_id_gui(rescrape) returned: {imdb_id}")
        if imdb_id:
            meta = get_entry(imdb_id)
            ui_debug_print(f"[CHECK] After get_entry(imdb_id) for rescrape: type(meta)={type(meta)}, meta={meta}")
            if not (meta is None or isinstance(meta, dict)):
                ui_debug_print(f"[ERROR] movies.process_file: meta is not a dict or None after rescrape! type={type(meta)}, value={meta}")
                meta = None
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
        # Try to extract an IMDb id from filename or parent folders before invoking GUI
        imdb_id = None
        try:
            # look in filename stem
            m = re.search(r"(tt\d{6,9})", file.stem)
            if not m:
                # search up to two parent folder names
                p = file.parent
                depth = 0
                while p and depth < 3:
                    mm = re.search(r"(tt\d{6,9})", p.name)
                    if mm:
                        m = mm
                        break
                    p = p.parent
                    depth += 1
            if m:
                imdb_id = m.group(1)
                ui_debug_print(f"[DBG] movies.process_file: extracted imdb id {imdb_id} from path for {file.name}")
            else:
                imdb_id = get_imdb_id_gui(file.name, search_title=orig_title)
        except Exception as e:
            print(f"[ERROR] movies.process_file: get_imdb_id_gui raised: {e}")
            raise
        ui_debug_print(f"[DBG] movies.process_file: get_imdb_id_gui returned: {imdb_id}")
        if imdb_id:
            meta = get_entry(imdb_id)
            ui_debug_print(f"[CHECK] After get_entry(imdb_id) for not found: type(meta)={type(meta)}, meta={meta}")
            if not (meta is None or isinstance(meta, dict)):
                ui_debug_print(f"[ERROR] movies.process_file: meta is not a dict or None after not found! type={type(meta)}, value={meta}")
                meta = None
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
    
    # Sanitize title to prevent path separator issues (e.g., "Naked Gun 33 1/3" -> "Naked Gun 33 1-3")
    meta_title_sanitized = meta_title.replace('/', '-').replace('\\', '-') if meta_title else meta_title
    
    extras = build_extras(orig_title, meta_title, orig_year, meta_year, orig_extras, old_imdb_id=imdb_id_in_name, new_imdb_id=imdb_id)

    filename = build_new_filename(meta_title_sanitized, meta_year, extras, imdb_id, file.suffix)
    folder_name = f"{meta_title_sanitized} ({meta_year})" if CREATE_MOVIE_SUBFOLDERS else ""
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
    #print(f"✅ Moved: {src.name}")
    print(f"✅ Finished: {src.name}")



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
            try:
                process_file(file, planned=planned, skipped=skipped)
            except Exception as e:
                # Log file-level exception and continue - this helps identify offending file
                try:
                    from config import debug_print
                    import traceback
                    debug_print(f"[ERROR] plan_movie_renames: process_file raised for {file}: {e}")
                    debug_print(traceback.format_exc())
                except Exception:
                    pass
                continue
    except KeyboardInterrupt:
        print("🚫 Cancelled by user.")
        for msg in skipped:
            print(msg)

        # Debug: log planned entries types and contents to help trace bad entries
        try:
            from config import debug_print
            for idx, entry in enumerate(planned):
                debug_print(f"[DEBUG] plan_movie_renames: planned[{idx}] type={type(entry).__name__} keys={list(entry.keys()) if isinstance(entry, dict) else 'N/A'} repr={repr(entry)}")
        except Exception:
            pass
    return planned

