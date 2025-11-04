omdb_request_count = 0
#omdb_gui_scraper

import json
import time
import requests
import re
import tkinter as tk
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageTk
from config import OMDB_API_KEY, OMDB_BASE_URL, OMDB_REQUEST_DELAY, OMDB_SEARCH_LIMIT, USER_AGENTS, IMDB_CACHE_FILE, debug_print
from typing import Optional, Callable, Any, Union, cast, Dict, List, Tuple
import threading
from core.media_metadata_cache import set_entry, update_entry, add_episode_to_series, get_entry
from actions.custom_imdb_web_poster_scraper import fetch_poster_url_and_store, scrape_full_movie_metadata

_root: Optional[tk.Tk] = None

def set_root(root_instance: tk.Tk) -> None:
    global _root
    # print(f"[DEBUG] set_root called with: {type(root_instance)}")
    debug_print(f"[DEBUG] set_root called with: {type(root_instance)}")
    _root = root_instance

def get_root() -> Any:
    if _root is None:
        raise RuntimeError("Root is not set yet (AppRoot not initialized)")
    if not hasattr(_root, "show_screen"):
        print(f"Root in get_root: {_root} of type {type(_root)}")
        raise RuntimeError("Root does not support 'show_screen'. Did you call set_root() with AppRoot?")
    if threading.current_thread() != threading.main_thread():
        raise RuntimeError("UI access attempted from non-main thread!")
    return _root

# ---- UI-safe request wrappers ----

def safe_request(func: Callable, *args: Any, message: str = "Loading...", delay: float = OMDB_REQUEST_DELAY, **kwargs: Any) -> Any:
    root = get_root()
    from config import ui_debug_print
    ui_debug_print(f"[SAFE_REQUEST] Starting safe_request for {getattr(func, '__name__', str(func))} message='{message}'")
    overlay = tk.Toplevel(root)
    overlay.transient(root)
    overlay.title("Please wait...")
    overlay.geometry("300x100+400+300")

    label = tk.Label(overlay, text=message, font=("Arial", 12))
    label.pack(expand=True, fill="both", pady=20)

    result: list[Any] = [None]
    # Make the variable owned by the app root so wait_variable works reliably
    done_var = tk.BooleanVar(root)

    # Run the potentially-blocking function in a background thread and use
    # root.after to set done_var from the main thread when finished.
    def worker():
        try:
            res = func(*args, **kwargs)
        except Exception as e:
            res = e

        def finish():
            result[0] = res
            try:
                done_var.set(True)
            except Exception:
                # If setting the var fails for any reason, still ensure overlay removed
                pass

        try:
            root.after(0, finish)
        except Exception:
            # As a fallback, set directly (may be unsafe on some Tk implementations)
            result[0] = res
            try:
                done_var.set(True)
            except Exception:
                pass

    import threading as _threading
    try:
        _threading.Thread(target=worker, daemon=True).start()
    except Exception:
        # If thread spawn fails, fall back to synchronous execution to preserve behaviour
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            result[0] = e
        try:
            done_var.set(True)
        except Exception:
            pass

    # Wait for worker to signal completion via the root-owned variable
    root.wait_variable(done_var)
    try:
        overlay.destroy()
    except Exception as e:
        debug_print(f"[SAFE_REQUEST] overlay.destroy() raised: {e}")
    # brief pause to avoid hammering external APIs when requested
    if delay:
        try:
            time.sleep(delay)
        except Exception:
            pass
    ui_debug_print(f"[SAFE_REQUEST] Finished safe_request for {getattr(func, '__name__', str(func))}")
    return result[0]

def safe_download_image(url: str, size: Tuple[int, int] = (60, 90), message: str = "Downloading image...") -> Optional[ImageTk.PhotoImage]:
    def download() -> ImageTk.PhotoImage:
        resp = requests.get(url, timeout=5)
        img = Image.open(BytesIO(resp.content)).resize(size)
        return ImageTk.PhotoImage(img)

    return safe_request(download, message=message, delay=0)

# ---- Cache & API setup ----

CACHE_FILE = IMDB_CACHE_FILE
SEARCH_LIMIT = OMDB_SEARCH_LIMIT
REQUEST_DELAY = OMDB_REQUEST_DELAY

if CACHE_FILE.exists():
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        imdb_cache: Dict[str, str] = json.load(f)
else:
    imdb_cache = {}

def save_cache() -> None:
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(imdb_cache, f, indent=2, ensure_ascii=False)

# def parse_title(title_line: str) -> tuple[str, Optional[str]]:
#     line = title_line.strip().strip('"')
#     year = None
#     match = re.search(r'\((\d{4})\)', line)
#     if match:
#         year = match.group(1)
#         line = re.sub(r'\s*\(\d{4}\)', '', line)
#     line = re.split(r'[-:]', line)[0].strip()
#     return line, year
# def parse_title(title_line: str) -> tuple[str, Optional[str]]:
#     line = title_line.strip().strip('"')
#     year = None
#     match = re.search(r'\((\d{4})\)', line)
#     if match:
#         year = match.group(1)
#         line = re.sub(r'\s*\(\d{4}\)', '', line)
#     return line.strip(), year
def parse_title(title_line: str) -> Tuple[str, Optional[str]]:
    # --- Clean raw filename or title string ---
    line = Path(title_line).stem  # remove file extension
    line = line.replace('.', ' ').replace('_', ' ')  # replace separators with spaces
    line = line.strip().strip('"')  # remove leading/trailing whitespace and quotes

    # --- Try to extract (YYYY) format ---
    year = None
    match = re.search(r'\((\d{4})\)', line)
    if match:
        year = match.group(1)
        line = re.sub(r'\s*\(\d{4}\)', '', line)  # remove the year from title

    return line.strip(), year


def search_omdb(title: str) -> List[Dict[str, Any]]:
    params = {'apikey': OMDB_API_KEY, 's': title}
    global omdb_request_count
    try:
        omdb_request_count += 1
        print(f"[OMDb] Request #{omdb_request_count}: {OMDB_BASE_URL} params={params}")
        resp = requests.get(OMDB_BASE_URL, params=params, timeout=10)
        data = resp.json()
        return data.get('Search', []) if data.get('Response') == 'True' else []
    except Exception:
        return []

# ---- GUI Picker ----
from gui.picker import Picker

# ---- GUI Flow ----

def get_imdb_id_gui(raw_line: str, max_retries: int = 3, search_title: Optional[str] = None, force_prompt: bool = False) -> Optional[str]:
    """
    raw_line: The full filename or folder name (for display to user)
    search_title: The cleaned title for searching/caching (optional, will be parsed from raw_line if not provided)
    imdb_cache is keyed by search_title for reliability.
    """
    if search_title is None:
        search_title, _ = parse_title(raw_line)
    cached_id = imdb_cache.get(search_title)

    # Only prompt if the cache is missing or the title/year is missing or mismatched, unless force_prompt is True
    if cached_id and not force_prompt:
        # Use metadata cache to check for title/year
        meta = get_entry(cached_id)
        if meta and meta.get('title') and meta.get('year'):
            return cached_id
        else:
            print(f"[INFO] Cached IMDb ID found") #but title/year may be incomplete. Re-prompting.
            return

    for attempt in range(max_retries):
        from config import ui_debug_print
        ui_debug_print(f"[DBG] get_imdb_id_gui: attempt {attempt+1}/{max_retries} for '{raw_line}' (search_title='{search_title}')")
        search_results = safe_request(search_omdb, search_title, message=f"Searching for '{search_title}'...")
        ui_debug_print(f"[DBG] get_imdb_id_gui: search returned {len(search_results)} results")
        ui_debug_print("[DBG] get_imdb_id_gui: showing Picker frame via show_screen")
        picker = get_root().show_screen(Picker, raw_line, search_title, search_results)
        ui_debug_print(f"[DBG] get_imdb_id_gui: picker created: {picker}; waiting for picker.done_var")
        try:
            get_root().wait_variable(picker.done_var)
        except Exception as e:
            debug_print(f"[ERROR] get_imdb_id_gui: wait_variable raised: {e}")
            # Re-raise so caller can handle cancellation as before
            raise
        ui_debug_print("[DBG] get_imdb_id_gui: picker.done_var set; reading picker state")
        # Read data before destroying picker
        result = None
        # Log picker flags for diagnostics
        ui_debug_print(f"[DBG] picker state: skipped={getattr(picker, 'skipped', False)}, cancelled={getattr(picker, 'cancelled', False)}, selection={getattr(picker, 'selection', None)}")
        if getattr(picker, "skipped", False):
            debug_print(f"[INFO] User skipped file: {raw_line}")
            result = None
        elif picker.cancelled:
            debug_print(f"[INFO] User cancelled picker for: {raw_line}")
            raise KeyboardInterrupt("User cancelled IMDb matching.")
        elif picker.selection:
            imdb_id = picker.selection['imdbID']
            debug_print(f"[INFO] User selected imdbID={imdb_id} for '{raw_line}'")
            # Persist mapping in imdb_cache (small file) so subsequent runs are faster
            imdb_cache[search_title] = imdb_id
            save_cache()
            ui_debug_print(f"[DBG] get_imdb_id_gui: imdb_cache updated for '{search_title}' -> '{imdb_id}' and saved")

            # Destroy the picker BEFORE performing any heavy metadata fetch/update to keep UI responsive
            try:
                try:
                    get_root().update_idletasks()
                except Exception:
                    pass
                picker.destroy()
                ui_debug_print("[DBG] get_imdb_id_gui: picker destroyed before further processing")
            except Exception as e:
                debug_print(f"[ERROR] get_imdb_id_gui: error destroying picker early: {e}")

            # If the user entered a manual IMDb ID (search term starting with 'tt'),
            # perform the full scrape safely (off the immediate callback) so we
            # populate the metadata cache without blocking the GUI.
            if picker.search_term.get().strip().lower().startswith("tt"):
                try:
                    ui_debug_print(f"[DBG] get_imdb_id_gui: calling scrape_full_movie_metadata for {imdb_id} via safe_request")
                    safe_request(scrape_full_movie_metadata, imdb_id, message=f"Scraping IMDb for {imdb_id}...")
                except Exception:
                    # If scraping fails, continue without blocking the selection flow
                    pass
            else:
                # For regular selections fetched from OMDb, try to get title/year
                ui_debug_print(f"[DBG] get_imdb_id_gui: fetching title/year for {imdb_id}")
                data = fetch_title_and_year_from_imdb_id(imdb_id)
                if data:
                    title_str, year_str = data
                    update_entry(imdb_id, {'title': title_str, 'year': year_str})
                    ui_debug_print(f"[DBG] get_imdb_id_gui: updated media cache for {imdb_id} title={title_str} year={year_str}")
            result = imdb_id
        else:
            print(f"[WARN] No valid selection on attempt {attempt + 1}/{max_retries}")
        ui_debug_print("[DBG] get_imdb_id_gui: destroying picker and continuing")
        try:
            # ensure any pending UI updates are processed before destroying
            try:
                get_root().update_idletasks()
            except Exception:
                pass
            picker.destroy()
        except Exception as e:
            debug_print(f"[ERROR] get_imdb_id_gui: error destroying picker: {e}")
        if result is not None:
            return result

    print(f"[INFO] Max retries reached for '{raw_line}'. Prompting manual IMDb ID entry.")
    fallback_id = manual_fallback_prompt(raw_line)
    if fallback_id:
        imdb_cache[search_title] = fallback_id
        save_cache()
        # Fallback: If it's a movie, scrape metadata from IMDb and update cache
        # Only do this if not already in metadata
        meta = get_entry(fallback_id)
        if not meta or not (meta.get('title') and meta.get('year')):
            print(f"[FALLBACK] Scraping IMDb for {fallback_id}...")
            scrape_full_movie_metadata(fallback_id)
    return fallback_id


def get_series_imdb_id_gui(raw_line: str, max_retries: int = 3, search_title: Optional[str] = None) -> Optional[str]:
    """
    raw_line: The full folder name (for display to user)
    search_title: The cleaned show title for searching/caching (optional, will be parsed from raw_line if not provided)
    imdb_cache is keyed by search_title for reliability.
    """
    if search_title is None:
        search_title, _ = parse_title(raw_line)
    cached_id = imdb_cache.get(search_title)
    if cached_id:
        # Use metadata cache to check for title/year
        meta = get_entry(cached_id)
        if meta and meta.get('title') and meta.get('year'):
            return cached_id
        else:
            # Try to fetch and update
            data = fetch_title_and_year_from_imdb_id(cached_id)
            if data:
                update_entry(cached_id, {'title': data[0], 'year': data[1]})
                return cached_id

    for attempt in range(max_retries):
        from config import ui_debug_print
        ui_debug_print(f"[DBG] get_series_imdb_id_gui: attempt {attempt+1}/{max_retries} for '{raw_line}' (search_title='{search_title}')")
        search_results = safe_request(search_omdb, search_title, message=f"Searching for series '{search_title}'...")
        ui_debug_print(f"[DBG] get_series_imdb_id_gui: search returned {len(search_results)} results")
        ui_debug_print("[DBG] get_series_imdb_id_gui: showing Picker frame via show_screen")
        picker = get_root().show_screen(Picker, raw_line, search_title, search_results)
        ui_debug_print(f"[DBG] get_series_imdb_id_gui: picker created: {picker}; waiting for picker.done_var")
        try:
            get_root().wait_variable(picker.done_var)
        except Exception as e:
            debug_print(f"[ERROR] get_series_imdb_id_gui: wait_variable raised: {e}")
            raise
        ui_debug_print("[DBG] get_series_imdb_id_gui: picker.done_var set; reading picker state")
        # Read data before destroying picker
        result = None
        ui_debug_print(f"[DBG] picker state (series): skipped={getattr(picker, 'skipped', False)}, cancelled={getattr(picker, 'cancelled', False)}, selection={getattr(picker, 'selection', None)}")
        if picker.cancelled:
            debug_print(f"[INFO] User cancelled series picker for: {raw_line}")
            try:
                picker.destroy()
            except Exception as e:
                debug_print(f"[ERROR] get_series_imdb_id_gui: error destroying picker after cancel: {e}")
            raise KeyboardInterrupt("User cancelled series matching.")
        elif picker.selection:
            imdb_id = picker.selection.get('imdbID') or picker.selection.get('id')
            if imdb_id:
                debug_print(f"[INFO] User selected series imdbID={imdb_id} for '{raw_line}'")
                imdb_cache[search_title] = imdb_id
                save_cache()
                ui_debug_print(f"[DBG] get_series_imdb_id_gui: imdb_cache updated for '{search_title}' -> '{imdb_id}' and saved")

                # Destroy picker early to avoid blocking UI while we populate episodes/poster
                try:
                    try:
                        get_root().update_idletasks()
                    except Exception:
                        pass
                    picker.destroy()
                    ui_debug_print("[DBG] get_series_imdb_id_gui: picker destroyed before further processing")
                except Exception as e:
                    debug_print(f"[ERROR] get_series_imdb_id_gui: error destroying picker early: {e}")

                # Fetch and save title with years for metadata cache and populate episodes for newly-picked series.
                try:
                    # Use safe_request so the UI shows a "Please wait" overlay while we populate episodes
                    safe_request(fetch_title_and_year_from_imdb_id, imdb_id, True, False,
                                 message=f"Fetching metadata and episodes for {imdb_id}...")
                except Exception:
                    # If the safe request fails, fall back to a best-effort synchronous fetch
                    try:
                        fetch_title_and_year_from_imdb_id(imdb_id, populate_episodes=True, fetch_poster=False)
                    except Exception:
                        pass
                # After populating episodes, attempt to fetch poster using the custom scraper (less frequently used file)
                try:
                    safe_request(fetch_poster_url_and_store, imdb_id, message=f"Fetching poster for {imdb_id}...")
                except Exception:
                    try:
                        fetch_poster_url_and_store(imdb_id)
                    except Exception:
                        pass
                # fetch_title_and_year_from_imdb_id already updates the entry when possible; try to read returned title/year
                data = fetch_title_and_year_from_imdb_id(imdb_id, populate_episodes=False, fetch_poster=False)
                if data:
                    update_entry(imdb_id, {'title': data[0], 'year': data[1]})
                result = imdb_id
        else:
            print(f"[WARN] No selection made for series (attempt {attempt + 1}/{max_retries})")
        ui_debug_print("[DBG] get_series_imdb_id_gui: destroying picker and continuing")
        try:
            try:
                get_root().update_idletasks()
            except Exception:
                pass
            picker.destroy()
        except Exception as e:
            debug_print(f"[ERROR] get_series_imdb_id_gui: error destroying picker: {e}")
        if result is not None:
            return result

    print(f"[INFO] Max retries reached for '{raw_line}' (TV). Prompting manual entry.")
    fallback_id = manual_fallback_prompt(raw_line)
    if fallback_id:
        imdb_cache[search_title] = fallback_id
        save_cache()
        # Try to fetch and save title with years and populate episodes for manual entry
        try:
            safe_request(fetch_title_and_year_from_imdb_id, fallback_id, True, False,
                         message=f"Fetching metadata and episodes for {fallback_id}...")
        except Exception:
            try:
                fetch_title_and_year_from_imdb_id(fallback_id, populate_episodes=True, fetch_poster=False)
            except Exception:
                pass
        # After populating episodes, also fetch poster via the custom scraper
        try:
            safe_request(fetch_poster_url_and_store, fallback_id, message=f"Fetching poster for {fallback_id}...")
        except Exception:
            try:
                fetch_poster_url_and_store(fallback_id)
            except Exception:
                pass
        data = fetch_title_and_year_from_imdb_id(fallback_id, populate_episodes=False, fetch_poster=False)
        if data:
            update_entry(fallback_id, {'title': data[0], 'year': data[1]})
    return fallback_id


def fetch_episode_ids_omdb(series_imdb_id: str, episode_cache: Dict[str, Dict[int, Dict[int, str]]], save_episode_cache_func: Callable[[], None]) -> Dict[int, Dict[int, str]]:
    if series_imdb_id not in episode_cache:
        episode_cache[series_imdb_id] = {}

    all_episodes = episode_cache[series_imdb_id]

    # Try to use media_metadata cache first
    from core.media_metadata_cache import get_entry
    meta = get_entry(series_imdb_id)
    if meta and 'episodes' in meta:
        # meta['episodes'] is a dict: {season: {episode: {imdb_id, ...}}}
        for season_str, eps in meta['episodes'].items():
            try:
                season_num = int(season_str)
            except Exception:
                continue
            if season_num not in all_episodes:
                all_episodes[season_num] = {}
            for ep_str, epdata in eps.items():
                try:
                    ep_num = int(ep_str)
                except Exception:
                    continue
                # epdata in the media cache may be either a dict with fields or a plain imdb id string
                if isinstance(epdata, dict):
                    imdb_id = epdata.get('imdb_id') or epdata.get('imdbID') or epdata.get('id')
                else:
                    imdb_id = str(epdata) if epdata else None
                # Only add if we have an IMDb ID
                if imdb_id and imdb_id != 'N/A':
                    all_episodes[season_num][ep_num] = imdb_id

    # Always start at season 1, never 0. Use totalSeasons reported by OMDb to stop early.
    max_season: Optional[int] = None
    # We'll loop until we hit max_season (if known) or an upper cap
    for season in range(1, 100):
        # If OMDb reported a max_season previously, stop when we've gone past it
        if max_season is not None and season > max_season:
            break
        # If we already have all episodes for this season in all_episodes, skip OMDb request
        # We'll assume a season is complete if there is at least one episode for this season in all_episodes
        if season in all_episodes and all_episodes[season]:
            continue
        params = {'apikey': OMDB_API_KEY, 'i': series_imdb_id, 'Season': season}
        try:
            global omdb_request_count
            omdb_request_count += 1
            print(f"[OMDb] Request #{omdb_request_count}: {OMDB_BASE_URL} params={params}")
            # Perform the HTTP request directly here. When fetch_episode_ids_omdb is
            # invoked from a background worker (via safe_request), this will not block
            # the GUI. Calling safe_request here could attempt to access the Tk root
            # from a non-main thread, so avoid nested safe_request usage.
            resp = requests.get(OMDB_BASE_URL, params=params, timeout=10)
            data = resp.json()

            # If OMDb provides totalSeasons in the response, use it to limit further requests
            try:
                ts = data.get('totalSeasons')
                if ts:
                    # sometimes totalSeasons is returned as a string like '1'
                    max_season = int(ts)
            except Exception:
                # ignore parsing issues and continue defensively
                max_season = max_season

            if data.get('Response') != 'True' or 'Episodes' not in data:
                break

            # Defensive: skip if OMDb returns season 0
            season_num = int(data['Season'])
            if season_num == 0:
                continue
            # If OMDb told us how many seasons exist and we've requested beyond it,
            # stop after processing this season.
            if max_season is not None and season_num > max_season:
                # odd case: OMDb reports totalSeasons < season in response; stop
                break
            if season_num not in all_episodes:
                all_episodes[season_num] = {}

            for ep in data['Episodes']:
                try:
                    ep_num = int(ep['Episode'])
                    imdb_id = ep.get('imdbID')
                    if imdb_id and imdb_id != 'N/A':
                        all_episodes[season_num][ep_num] = imdb_id
                        # Fetch episode details and add to metadata
                        ep_title = ep.get('Title')
                        ep_year = ep.get('Released', '')[:4] if ep.get('Released') else ''
                        ep_data = {
                            'title': ep_title,
                            'year': ep_year,
                            'type': 'episode',
                            'summary': '',
                            'poster_url': ''
                        }
                        add_episode_to_series(series_imdb_id, str(season_num), str(ep_num), imdb_id, ep_data)
                except (ValueError, KeyError):
                    continue
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"❌ Failed fetching Season {season}: {e}")
            break

    return all_episodes

# def fetch_title_from_imdb_id(imdb_id: str) -> Optional[str]:
#     params = {'apikey': OMDB_API_KEY, 'i': imdb_id}
#     try:
#         resp = requests.get('http://www.omdbapi.com/', params=params, timeout=10)
#         data = resp.json()
#         if data.get('Response') == 'True':
#             return data.get('Title')
#     except Exception as e:
#         print(f"❌ Failed to fetch title for {imdb_id}: {e}")
#     return None

#temporary wrapper
def fetch_title_from_imdb_id(imdb_id: str) -> Optional[str]:
    data = fetch_title_and_year_from_imdb_id(imdb_id)
    return f"{data[0]} ({data[1]})" if data else None

def fetch_title_and_year_from_imdb_id(imdb_id: str, populate_episodes: bool = False, fetch_poster: bool = True) -> Optional[Tuple[str, str]]:
    """
    Fetch show/movie title and year from OMDb and persist into media cache.

    populate_episodes: if True, after fetching show-level data attempt to populate episode mapping (may make additional OMDb calls).
    fetch_poster: if True, run the IMDb web scraper to fetch poster_url (this makes an extra HTTP request).
    """
    params = {'apikey': OMDB_API_KEY, 'i': imdb_id}
    global omdb_request_count
    try:
        omdb_request_count += 1
        print(f"[OMDb] Request #{omdb_request_count}: {OMDB_BASE_URL} params={params}")
        resp = requests.get(OMDB_BASE_URL, params=params, timeout=10)
        data = resp.json()
        if data.get('Response') == 'True':
            title = data.get('Title')
            year = data.get('Year')
            plot = data.get('Plot')
            type_ = data.get('Type')
            ts = data.get('totalSeasons')

            # Merge/update logic: only add missing title/year/type or update when OMDb provides richer info
            try:
                existing = get_entry(imdb_id) or {}
            except Exception:
                existing = {}

            updates: Dict[str, Any] = {}

            # Title: add if missing
            if title and not existing.get('title'):
                updates['title'] = title

            # Year: add if missing, or replace if OMDb provides a range while cache has single year
            existing_year = existing.get('year')
            if year and not existing_year:
                updates['year'] = year
            elif year and existing_year:
                # Normalize check for range char
                def is_range(s: str) -> bool:
                    return (isinstance(s, str) and ('–' in s or '-' in s))
                if is_range(year) and not is_range(existing_year):
                    updates['year'] = year
                # otherwise prefer existing range over single-year OMDb responses

            # totalSeasons: persist if present
            if ts:
                try:
                    updates['totalSeasons'] = int(ts)
                except Exception:
                    updates['totalSeasons'] = ts

            # Type: prefer existing series if episodes already present; otherwise set from OMDb
            if existing.get('episodes'):
                # keep existing type (likely 'series') and do not overwrite with 'movie'
                pass
            else:
                if type_:
                    updates['type'] = type_

            # Summary: add if missing
            if plot and not existing.get('summary'):
                updates['summary'] = plot

            if updates:
                try:
                    update_entry(imdb_id, updates)
                except Exception:
                    pass

            # Optionally fetch poster (separate HTTP request)
            if fetch_poster:
                try:
                    fetch_poster_url_and_store(imdb_id)
                except Exception:
                    pass

            # Optionally populate episodes (may make multiple OMDb season requests)
            if populate_episodes and type_ == 'series':
                try:
                    try:
                        tsn = int(ts) if ts is not None else None
                    except Exception:
                        tsn = None
                    if tsn is None or tsn <= 50:
                        fetch_episode_ids_omdb(imdb_id, {}, lambda: None)
                except Exception:
                    pass

            # Ensure that if we have an episodes map, the stored type is 'series'
            try:
                post_meta = get_entry(imdb_id) or {}
                if post_meta.get('episodes') and post_meta.get('type') != 'series':
                    try:
                        update_entry(imdb_id, {'type': 'series'})
                    except Exception:
                        pass
            except Exception:
                pass

            return title, year
    except Exception as e:
        print(f"❌ Failed to fetch title/year for {imdb_id}: {e}")
    return None


# ---- Manual IMDb Entry ----

class ManualIMDbEntryScreen(tk.Frame):
    def __init__(self, master: Any, show: str, season: int, episode: int, on_submit: Callable[[Optional[str]], None]):
        super().__init__(master)
        self.result: Optional[str] = None
        self.on_submit_callback = on_submit

        tk.Label(self, text=f"Missing IMDb ID for {show} S{season:02}E{episode:02}",
                 font=("Arial", 12)).pack(pady=10)
        tk.Label(self, text="Enter IMDb episode ID or full URL:").pack()

        self.entry = tk.Entry(self, width=50)
        self.entry.pack(pady=5)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Submit", command=self.submit).pack(pady=10)
        tk.Button(btn_frame, text="Cancel", command=self.cancel, fg="red").pack(side='left', padx=5)

    def submit(self):
        text = self.entry.get().strip()
        match = re.search(r'(tt\d{7,})', text)
        if match:
            imdb_id = match.group(1)
            self.on_submit_callback(imdb_id)
        else:
            self.on_submit_callback(None)

    def cancel(self):
        self.on_submit_callback(None)
        self.destroy()

def complete_episode_ids_with_manual_gui(
    show: str,
    imdb_id: str,
    episode_ids: Dict[int, Dict[int, str]],
    detected_episodes: Any,
    season: Optional[int],
    episode: Optional[int]
) -> Optional[str]:
    if season is None or episode is None:
        return
    if episode_ids.get(season, {}).get(episode):
        return

    imdb_result: dict[str, Optional[str]] = {"value": None}
    done_var = tk.BooleanVar()

    def on_submit(ep_id: Optional[str]):
        imdb_result["value"] = ep_id
        done_var.set(True)

    get_root().bind("<Destroy>", lambda e: done_var.set(True))
    get_root().show_screen(ManualIMDbEntryScreen, show, season, episode, on_submit)
    get_root().wait_variable(done_var)
    get_root().unbind("<Destroy>")

    ep_id = imdb_result["value"]
    if ep_id:
        if season not in episode_ids:
            episode_ids[season] = {}
        episode_ids[season][episode] = ep_id
        print(f"✅ Manually assigned IMDb ID: {ep_id} for {show} S{season}E{episode}")
        return ep_id

    return None

def manual_fallback_prompt(raw_line: str) -> Optional[str]:
    """
    Prompt the user for a manual IMDb ID (or URL), extract the tt#######, and return it.
    Returns None if cancelled.
    """
    import tkinter as tk
    from tkinter import simpledialog, messagebox
    import re

    root = get_root()
    while True:
        user_input = simpledialog.askstring(
            "Manual IMDb ID Entry",
            f"Could not find IMDb ID for:\n\n{raw_line}\n\nPlease enter the IMDb ID (e.g. tt1234567) or full IMDb URL:",
            parent=root
        )
        if user_input is None:
            return None  # Cancelled
        match = re.search(r"tt\d{7,8}", user_input)
        if match:
            return match.group(0)
        messagebox.showerror("Invalid IMDb ID", "Please enter a valid IMDb ID (e.g. tt1234567) or IMDb URL.", parent=root)
