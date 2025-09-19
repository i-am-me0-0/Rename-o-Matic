"""
series.py
Main orchestration logic for series renamer. Utilities are imported from core/series_utils.py.
"""
from pathlib import Path
import shutil
import re
from core.file_utils import is_video_file
from core.series_utils import clean_brackets, get_folder_imdb_id, get_episode_imdb_id_from_filename
from core.info_extractors import extract_episode_info
from undo import log_rename
from config import SERIES_DIR, LANG_CODES, debug_print
from actions.omdb_gui_scraper import get_series_imdb_id_gui, fetch_episode_ids_omdb
from core.media_metadata_cache import (
    get_entry, get_episode_id_from_metadata, get_episode_info_by_id, load_metadata
)
from core.manual_episode_cache import load_manual_episode_cache, save_manual_episode_cache
from core.manual_episode_title_cache import load_manual_episode_title_cache, save_manual_episode_title_cache
from gui.episode_id_prompt import prompt_for_episode_id
from config import SKIP_IMDB_IDS
from core.series_utils import is_imdb_id_skipped
from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id, fetch_episode_ids_omdb


# --- Utility: Get all metadata entries (imdb_id, entry) ---
def get_all_metadata_entries():
    metadata = load_metadata()
    for mid, entry in metadata.items():
        yield mid, entry

# --- Utility: Clean brackets from IDs ---
def clean_brackets(text):
    cleaned = text.strip()
    if (cleaned.startswith("[") and cleaned.endswith("]")) or (cleaned.startswith("(") and cleaned.endswith(")")):
        cleaned = cleaned[1:-1].strip()
    return cleaned

# --- Step 1: Get or prompt for show IMDb ID (never for episode filenames) ---
def get_or_prompt_show_imdb_id(show, folder_name, show_id_map):
    # Always use the main series folder name as the cache key
    cache_key = folder_name
    if (show, cache_key) in show_id_map:
        return show_id_map[(show, cache_key)]

    # Load imdb_cache
    import json
    imdb_cache_path = Path(__file__).parent.parent / 'cache' / 'imdb_cache.json'
    try:
        with open(imdb_cache_path, 'r', encoding='utf-8') as f:
            imdb_cache = json.load(f)
    except Exception:
        imdb_cache = {}

    imdb_id = imdb_cache.get(cache_key)
    meta = get_entry(imdb_id) if imdb_id else None

    # If the id is for a movie, but we're processing a series, always prompt user to confirm or override
    if meta and meta.get('type') == 'movie':
        # Find all cache entries with the same folder/show name (case-insensitive)
        matches = []
        for k, v in imdb_cache.items():
            if k.lower().strip() == cache_key.lower().strip():
                alt_meta = get_entry(v)
                if alt_meta:
                    matches.append((v, alt_meta))
        from tkinter import Tk, simpledialog
        root = Tk()
        root.withdraw()
        options = []
        for v, m in matches:
            t = m.get('title', v)
            y = m.get('year', '')
            typ = m.get('type', '')
            options.append(f"{t} ({y}) [{typ}] - {v}")
        prompt_text = (f"The current IMDb ID for '{cache_key}' is a movie.\n\n" +
                       (('Multiple IMDb entries found:\n' + '\n'.join(f"{i+1}. {opt}" for i, opt in enumerate(options)) +
                        "\n\nEnter the number of the correct entry, or leave blank to search for a series:") if len(matches) > 1 else
                        f"Movie: {options[0]}\n\nType '1' to accept, or leave blank to search for a series:"))
        choice = simpledialog.askstring("Ambiguous Title", prompt_text)
        root.destroy()
        try:
            if choice is not None and choice.strip() != '':
                idx = int(choice) - 1
                if 0 <= idx < len(matches):
                    imdb_id = matches[idx][0]
                    meta = matches[idx][1]
            else:
                # User wants to search for a series instead
                imdb_id = get_series_imdb_id_gui(cache_key, search_title=show)
                meta = get_entry(imdb_id) if imdb_id else None
        except Exception:
            pass

    # If still not found or user wants to override, prompt as usual
    if not imdb_id or not meta or meta.get('type') != 'series':
        imdb_id = get_series_imdb_id_gui(cache_key, search_title=show)
        if imdb_id is None:
            debug_print(f"⏭️ Skipped by user: {cache_key}")
            return None
        meta = get_entry(imdb_id)
        if meta and meta.get('type') == 'series':
            # Only update cache if folder_name is not an ambiguous season folder (like 'S01', 's1', etc.)
            def is_ambiguous_season_folder(key):
                import re
                # Acceptable: 'Series Title S01', 'Series Title Season 1', etc.
                # Ambiguous: 'S01', 's1', 'Season 1', etc. (no prefix)
                season_patterns = [r'^(s\d+)$', r'^(S\d+)$', r'^(season \d+)$', r'^(Season \d+)$']
                for pat in season_patterns:
                    if re.match(pat, key.strip()):
                        return True
                return False
            if not is_ambiguous_season_folder(cache_key):
                imdb_cache[cache_key] = imdb_id
                try:
                    with open(imdb_cache_path, 'w', encoding='utf-8') as f:
                        json.dump(imdb_cache, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

    show_id_map[(show, cache_key)] = imdb_id
    return imdb_id

# --- Step 2: Lookup episode IMDb ID (media_metadata is canonical) ---
def lookup_episode_id(imdb_id, season, episode, file_stem=None):
    if file_stem:
        manual_title_cache = load_manual_episode_title_cache()
        ep_id = manual_title_cache.get(file_stem)
        if ep_id:
            return ep_id
    manual_episode_cache = load_manual_episode_cache()
    ep_id = manual_episode_cache.get(str(imdb_id), {}).get(str(season), {}).get(str(episode))
    if ep_id:
        return ep_id
    ep_id = get_episode_id_from_metadata(imdb_id, str(season), str(episode))
    if ep_id:
        return ep_id
    if season is None and episode is not None:
        meta = get_entry(imdb_id)
        if meta and 'episodes' in meta:
            for s, eps in meta['episodes'].items():
                for ep_num, ep_id in eps.items():
                    if str(ep_num) == str(episode):
                        return ep_id
    return None

# --- Step 3: Get or prompt for episode IMDb ID (never pollute imdb_cache.json) ---
def get_episode_imdb_id(show, imdb_id, season, episode, file_stem=None):
    ep_id = lookup_episode_id(imdb_id, season, episode, file_stem=file_stem)
    if ep_id:
        return ep_id
    if imdb_id:
        fetch_episode_ids_omdb(imdb_id, {}, lambda: None)
    ep_id = lookup_episode_id(imdb_id, season, episode, file_stem=file_stem)
    if ep_id:
        return ep_id
    if season is not None and episode is not None:
        prompt_title = f"{show} S{season}E{episode}"
    else:
        prompt_title = f"{show} (Special/Edge)"
    prompt_msg = f"Enter IMDb episode ID for: {prompt_title}"
    ep_id = prompt_for_episode_id(prompt_title, prompt_msg)
    if ep_id:
        manual_episode_cache = load_manual_episode_cache()
        manual_episode_cache.setdefault(str(imdb_id), {}).setdefault(str(season), {})[str(episode)] = ep_id
        save_manual_episode_cache(manual_episode_cache)
        if file_stem:
            manual_title_cache = load_manual_episode_title_cache()
            manual_title_cache[file_stem] = ep_id
            save_manual_episode_title_cache(manual_title_cache)
        return ep_id
    return None

# --- Step 4: Build output path for episode (robust, extras, specials, always append ep_id) ---
def build_episode_path(file, show, season, episode, extras, imdb_id, ep_id, original_file_stem=None):
    # Canonical series title and years from metadata
    series_title = show
    years_str = ""
    if imdb_id:
        meta = get_entry(imdb_id)
        if meta:
            if meta.get('title'):
                series_title = meta['title']
            # Try to get years info
            start_year = meta.get('year')
            end_year = meta.get('end_year')
            # Accept 'year' as int or str
            if start_year:
                try:
                    start_year = str(start_year)
                except Exception:
                    pass
            if end_year:
                try:
                    end_year = str(end_year)
                except Exception:
                    pass
            if start_year and end_year and start_year != end_year:
                years_str = f" ({start_year}-{end_year})"
            elif start_year:
                years_str = f" ({start_year})"
            # If no year info, leave blank
    # Canonical episode info from metadata
    override_season, override_episode = season, episode
    ep_info = get_episode_info_by_id(ep_id) if ep_id else None
    canonical_ep_title = None
    is_movie_cut_special = False
    if ep_info:
        # If OMDb type is 'movie' but we're in a series context, treat as special
        if ep_info.get('type') == 'movie' and imdb_id:
            override_season = 0
            override_episode = 0
            is_movie_cut_special = True
        if ep_info.get('season') is not None:
            override_season = int(ep_info['season'])
        if ep_info.get('episode') is not None:
            override_episode = int(ep_info['episode'])
        if ep_info.get('series_title'):
            series_title = ep_info['series_title']
        # Try to get canonical episode title
        if ep_info.get('title'):
            canonical_ep_title = ep_info['title']
    # Build extras (deduplicate, always include non-canonical info)
    extras_out = []
    # For regular episodes, prefer canonical episode title as the only extra
    if override_season is not None and override_episode is not None and not is_movie_cut_special:
        if canonical_ep_title:
            extras_out.append(str(canonical_ep_title))
        elif extras:
            extras_out.append(str(extras))
    # For edge/specials or movie-cut specials, always include original file stem as extra
    if (season is None or episode is None or is_movie_cut_special) and original_file_stem:
        extras_out.append(original_file_stem)
        if is_movie_cut_special:
            extras_out.append("Movie Cut")
    # Remove duplicates and empty extras
    seen = set()
    deduped_extras = []
    for e in extras_out:
        if e and e not in seen:
            deduped_extras.append(e)
            seen.add(e)
    # Compose filename
    if override_season is not None and override_episode is not None:
        if override_season == 0:
            season_folder = "Season 00 - Specials"
        else:
            season_folder = f"Season {override_season:02}"
        episode_name = f"{series_title} - S{override_season:02}E{override_episode:02}"
    else:
        season_folder = "Season 00 - Specials"
        episode_name = f"{series_title} - S00E00"
    # Add extras if any
    if deduped_extras:
        extras_str = " - ".join([e for e in deduped_extras if e])
        if extras_str and extras_str not in episode_name:
            episode_name += f" [{extras_str}]"
    # Always append episode IMDb ID
    if ep_id:
        cleaned_ep_id = clean_brackets(ep_id)
        if cleaned_ep_id not in episode_name:
            episode_name += f" [{cleaned_ep_id}]"
    # Compose show folder name with years and IMDb ID
    show_folder = f"{series_title}{years_str} [{imdb_id}]" if imdb_id else series_title
    dest_folder = SERIES_DIR / show_folder / season_folder
    dest_path = dest_folder / (episode_name + file.suffix)
    return dest_folder, dest_path

# --- Step 5: Move/rename video and subtitles together (preserve language codes) ---
def move_series_with_subtitles(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)

    subtitle_files = []
    for lang_code in LANG_CODES:
        suffix = f".{lang_code}.srt" if lang_code else ".srt"
        sub_file = src.with_suffix(suffix)
        if sub_file.exists():
            subtitle_files.append(sub_file)

    shutil.move(str(src), str(dest))

    moved_subtitles = []
    for sub_file in subtitle_files:
        new_sub_path = dest.with_suffix(sub_file.suffix)
        shutil.move(str(sub_file), str(new_sub_path))
        moved_subtitles.append((sub_file, new_sub_path))

    log_rename(src, dest, moved_subtitles)
    print(f"✅ Moved: {src.name}")

# --- Step 6: Plan all series renames (batch, robust, preview) ---
def plan_series_renames():
    debug_print("[DEBUG] --- Starting plan_series_renames ---")
    debug_print(f"[DEBUG] SKIP_IMDB_IDS: {SKIP_IMDB_IDS}")
    planned = []
    show_id_map = {}
    
    # Group files by series folder
    series_files = {}
    for file in SERIES_DIR.rglob("*"):
        if not (file.is_file() and is_video_file(file)):
            continue
        folder_name = file.parent.name
        series_files.setdefault(folder_name, []).append(file)
    
    for folder_name, files in series_files.items():
        debug_print(f"Processing folder: {folder_name}")
        # Step 1: Check for IMDb ID in folder name
        folder_imdb_id = get_folder_imdb_id(folder_name)

        # Step 2: If folder IMDb ID is in skip list, only add missing episode IDs, skip further renaming
        debug_print(f"Folder IMDb ID: {folder_imdb_id}")
        if is_imdb_id_skipped(folder_imdb_id, folder_name):
            debug_print(f"📁 Skipping entire series (folder IMDb ID in skip list): {folder_name}")
            if folder_imdb_id:
                meta = get_entry(folder_imdb_id)
                if not meta:
                    fetch_title_and_year_from_imdb_id(folder_imdb_id)
                meta = get_entry(folder_imdb_id)
                if meta and meta.get('type') == 'series':
                    fetch_episode_ids_omdb(folder_imdb_id, {}, lambda: None)
            for file in files:
                debug_print(f"  Processing file: {file.name}")
                show, season, episode, extras = extract_episode_info(file.stem)
                ep_imdb_id = get_episode_imdb_id_from_filename(file.stem)
                # If episode already has an IMDb ID, skip outright
                if ep_imdb_id:
                    debug_print(f"✓ Skipped episode (already has IMDb ID): {file.name} (ID: {ep_imdb_id})")
                    continue
                # Add episode IMDb ID if missing
                if folder_imdb_id and season and episode:
                    ep_id = lookup_episode_id(folder_imdb_id, season, episode)
                    debug_print(f"  lookup_episode_id result: {ep_id}")
                    if ep_id:
                        debug_print(f"Adding missing episode ID to: {file.name}")
                        new_stem = file.stem + f"[{ep_id}]"
                        new_path = file.parent / (new_stem + file.suffix)
                        shutil.move(str(file), str(new_path))
                        planned.append({
                            "type": "Series",
                            "src": str(file),
                            "dest": str(new_path)
                        })
                        debug_print(f"Planned ADD ONLY IMDb ID for skipped folder: {file.name} -> {new_path}")
                else:
                    debug_print(f"No season/episode info for: {file.name}")
            continue
# ... (previous code remains the same until the file processing loop)
        # Step 3: Regular processing for files not in skip list
        # for file in files:
        #     debug_print(f"  Processing file: {file.name}")
        #     show, season, episode, extras = extract_episode_info(file.stem)
        #     if not show:
        #         continue

        #     # Step 4: Check for IMDb ID in filename
        #     ep_imdb_id = get_episode_imdb_id_from_filename(file.stem)
        #     # If episode already has an IMDb ID and it's in skip list, skip outright
        #     if ep_imdb_id and is_imdb_id_skipped(ep_imdb_id, file.name):
        #         debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_imdb_id})")
        #         continue

        #     # Step 5: Get or prompt for show IMDb ID
        #     imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
        #     if imdb_id is None:
        #         debug_print(f"⏭️ Skipped by user: {file.name}")
        #         continue

        #     # Step 6: Always resolve episode IMDb ID (from filename or lookup)
        #     ep_id = ep_imdb_id if ep_imdb_id else get_episode_imdb_id(show, imdb_id, season, episode)

        #     # Step 7: If resolved episode IMDb ID is in skip list, skip outright
        #     if ep_id and is_imdb_id_skipped(ep_id, file.name):
        #         debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_id})")
        #         continue

        for file in files:
            debug_print(f"  Processing file: {file.name}")
            show, season, episode, extras = extract_episode_info(file.stem)
        
            # Early exit if no valid show name
            if not show:
                continue
                
            # Step 1: Check for IMDb ID in filename
            ep_imdb_id = get_episode_imdb_id_from_filename(file.stem)
            
            # Skip if filename IMDb ID is in skip list
            if ep_imdb_id and is_imdb_id_skipped(ep_imdb_id, file.name):
                debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_imdb_id})")
                continue
            
            # Step 2: Get or prompt for show IMDb ID
            imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
            if imdb_id is None:
                debug_print(f"⏭️ Skipped by user: {file.name}")
                continue
                
            # Step 3: Resolve episode IMDb ID
            ep_id = get_episode_imdb_id(show, imdb_id, season, episode)
            
            # Skip if resolved ID is in skip list
            if ep_id and is_imdb_id_skipped(ep_id, file.name):
                debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_id})")
                continue

            #--... (rest of the function remains the same)

            # Step 8: Continue with full metadata-driven renaming
            fetch_episode_ids_omdb(imdb_id, {}, lambda: None)
            _, dest_path = build_episode_path(file, show, season, episode, extras, imdb_id, ep_id)
            if file.resolve() == dest_path.resolve():
                debug_print(f"⏭️ Skipping (already correctly named): {file.relative_to(SERIES_DIR)}")
                continue

            planned.append({
                "type": "Series",
                "src": str(file),
                "dest": str(dest_path)
            })
            debug_print(f"Planned FULL RENAME: {file.name} -> {dest_path}")


# --- Step 7: Rename (move) a single series file and its subtitles ---
def organize_series(preview_only: bool, selected_files=None):
    show_id_map = {}

    try:
        for file in SERIES_DIR.rglob("*"):
            if not (file.is_file() and is_video_file(file)):
                continue
            if selected_files and str(file) not in selected_files:
                continue

            show, season, episode, extras = extract_episode_info(file.stem)
            if not show:
                debug_print(f"❌ Skipping (unparsed): {file.name}")
                continue

            imdb_id = get_or_prompt_show_imdb_id(show, file.parent.name, show_id_map)
            ep_id = get_episode_imdb_id(show, imdb_id, season, episode)
            dest_folder, dest_path = build_episode_path(file, show, season, episode, extras, imdb_id, ep_id)

            print(f"\nEpisode: {file.relative_to(SERIES_DIR.parent)}\n -> {dest_path.relative_to(SERIES_DIR)}")

            if file.resolve() == dest_path.resolve():
                debug_print(f"⏭️ Skipping (already correctly named): {file.relative_to(SERIES_DIR)}")
                continue

            if preview_only:
                continue

            if dest_path.exists():
                print(f"⚠️ Already exists, skipping: {dest_path.relative_to(SERIES_DIR)}")
                continue

            move_series_with_subtitles(file, dest_path)

    except KeyboardInterrupt:
        print("🚫 Cancelled by user.")

# --- Step 8: Organize all series (batch, robust, preview or execute) ---
def rename_series(src: Path, dest: Path):
    move_series_with_subtitles(src, dest)


# --- Step 9: Batch GUI prompt for missing episode IDs (for edge/specials) ---
def plan_series_renames_with_gui_prompts(root=None):
    from gui.episode_id_prompt import EpisodeIDPrompt
    planned = []
    show_id_map = {}
    show_files = {}
    manual_title_cache = load_manual_episode_title_cache()
    imdb_cache = {}
    # Load imdb_cache.json for folder-based lookup
    try:
        import json
        with open(str(Path(__file__).parent.parent / 'cache' / 'imdb_cache.json'), 'r', encoding='utf-8') as f:
            imdb_cache = json.load(f)
    except Exception:
        pass
    # Collect all files by show
    for file in SERIES_DIR.rglob("*"):
        if not (file.is_file() and is_video_file(file)):
            continue
        show, season, episode, extras = extract_episode_info(file.stem)
        if not show:
            continue
        folder_name = file.parent.name
        show_files.setdefault((show, folder_name), []).append((file, season, episode, extras))
    # For each show, always use folder name to look up series IMDb ID, then prompt for missing episodes
    for (show, folder_name), files in show_files.items():
        # Prefer folder_name for imdb_cache lookup, fallback to show
        imdb_id = imdb_cache.get(folder_name) or imdb_cache.get(show)
        if not imdb_id:
            imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
            if not imdb_id:
                debug_print(f"⏭️ Skipped fetching OMDb data for show: {show} (no IMDb ID)")
                continue
        fetch_episode_ids_omdb(imdb_id, {}, lambda: None)
        # Check for missing episodes
        missing_episodes = []
        episode_map = {}
        for file, season, episode, extras in files:
            ep_id = None
            if file.stem in manual_title_cache:
                ep_id = manual_title_cache[file.stem]
            elif season is not None and episode is not None:
                ep_id = lookup_episode_id(imdb_id, season, episode)
            if not ep_id:
                missing_episodes.append((file, season, episode, extras))
            else:
                episode_map[(season, episode)] = ep_id
        # Batch prompt for missing episode IDs
        if missing_episodes and root is not None:
            def on_submit(epid_map):
                manual_episode_cache = load_manual_episode_cache()
                for idx, (file, season, episode, extras) in enumerate(missing_episodes):
                    key = f"S{season or 'X'}E{episode or 'X'}: {file.name}"
                    ep_id = epid_map.get(key, "")
                    if ep_id and imdb_id:
                        manual_episode_cache.setdefault(str(imdb_id), {}).setdefault(str(season), {})[str(episode)] = ep_id
                        save_manual_episode_cache(manual_episode_cache)
                    manual_title_cache = load_manual_episode_title_cache()
                    if file.stem and ep_id:
                        manual_title_cache[file.stem] = ep_id
                        save_manual_episode_title_cache(manual_title_cache)
                root.quit()
            prompt_list = [f"S{season or 'X'}E{episode or 'X'}: {file.name}" for (file, season, episode, extras) in missing_episodes]
            prompt = EpisodeIDPrompt(root, f"{show} | Folder: {folder_name}", prompt_list, on_submit, file_names=[file.name for (file,_,_,_) in missing_episodes])
            root.wait_window(prompt)
        for file, season, episode, extras in files:
            ep_id = None
            if file.stem in manual_title_cache:
                ep_id = manual_title_cache[file.stem]
            elif season is not None and episode is not None:
                ep_id = lookup_episode_id(imdb_id, season, episode, file_stem=file.stem)
            else:
                ep_id = lookup_episode_id(imdb_id, season, episode, file_stem=file.stem)
            _, dest_path = build_episode_path(file, show, season, episode, extras, imdb_id, ep_id, original_file_stem=file.stem)
            if file.resolve() != dest_path.resolve():
                planned.append({
                    "type": "Series",
                    "src": str(file),
                    "dest": str(dest_path)
                })
    return planned








# ---------- Main Functionalities ----------








