"""
series.py
Main orchestration logic for series renamer. Utilities are imported from core/series_utils.py.
"""
from pathlib import Path
import shutil
import re
import json
import os
from core.file_utils import is_video_file
from core.series_utils import clean_brackets, get_folder_imdb_id
from core.info_extractors import extract_episode_info
from undo import log_rename
from config import SERIES_DIR, LANG_CODES, debug_print, ui_debug_print 
from actions.omdb_gui_scraper import get_series_imdb_id_gui, fetch_episode_ids_omdb
from core.media_metadata_cache import (
    get_entry, get_episode_id_from_metadata, get_episode_info_by_id, load_metadata
)
import tkinter as tk
from core.manual_episode_cache import load_manual_episode_cache, save_manual_episode_cache
from core.manual_episode_title_cache import load_manual_episode_title_cache, save_manual_episode_title_cache
from gui.episode_id_prompt import prompt_for_episode_id, EpisodeIDPrompt, EpisodeIDPromptFrame
from config import SKIP_IMDB_IDS
from core.series_utils import is_imdb_id_skipped
from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id, fetch_episode_ids_omdb
# Use GUI-based IMDb conflict prompt from gui package
from gui.imdb_conflict_prompt import prompt_for_imdb_id_conflict

# Module-level imdb_cache helpers used by multiple functions
imdb_cache_path = Path(__file__).parent.parent / 'cache' / 'imdb_cache.json'

def load_imdb_cache():
    try:
        with open(imdb_cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_imdb_cache(cache):
    try:
        tmp_path = imdb_cache_path.with_suffix('.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        try:
            os.replace(tmp_path, imdb_cache_path)
        except Exception:
            try:
                tmp_path.rename(imdb_cache_path)
            except Exception:
                pass
    except Exception:
        pass


# --- Utility: Get all metadata entries (imdb_id, entry) ---
def get_all_metadata_entries():
    """Yield (imdb_id, metadata_entry) for every entry in the media metadata cache.

    This tiny generator is used by other helpers that need to iterate the media cache.
    """
    metadata = load_metadata()
    for mid, entry in metadata.items():
        yield mid, entry

# --- Utility: Clean brackets from IDs ---
def clean_brackets(text):
    """Remove surrounding [] or () from a string and trim whitespace.

    Used often for cleaning IMDb IDs stored in filenames like "[tt1234567]".
    """
    cleaned = text.strip()
    if (cleaned.startswith("[") and cleaned.endswith("]")) or (cleaned.startswith("(") and cleaned.endswith(")")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _episode_numbers(episode):
    if isinstance(episode, (list, tuple, set)):
        out = []
        for item in episode:
            try:
                out.append(int(item))
            except Exception:
                continue
        return out
    try:
        if episode is None:
            return []
        return [int(episode)]
    except Exception:
        return []


def _format_episode_label(season, episode):
    nums = _episode_numbers(episode)
    if season is None or not nums:
        return "Special/Edge"
    try:
        s_num = int(season)
        if len(nums) == 1:
            return f"S{s_num:02}E{nums[0]:02}"
        return f"S{s_num:02}E{nums[0]:02}" + "".join([f"-E{n:02}" for n in nums[1:]])
    except Exception:
        return "Special/Edge"


def _episode_id_list(ep_id):
    if not ep_id:
        return []
    if isinstance(ep_id, (list, tuple, set)):
        return [str(x) for x in ep_id if x]
    if isinstance(ep_id, str) and "|" in ep_id:
        return [part.strip() for part in ep_id.split("|") if part.strip()]
    return [str(ep_id)]


def _has_skipped_episode_id(ep_id, name):
    for eid in _episode_id_list(ep_id):
        if is_imdb_id_skipped(eid, name):
            return True
    return False


def _get_episode_ids_from_filename(file_stem):
    try:
        matches = re.findall(r"tt\d{7,9}", str(file_stem))
    except Exception:
        matches = []
    if not matches:
        return None
    cleaned = []
    seen = set()
    for m in matches:
        cid = clean_brackets(m)
        if cid and cid not in seen:
            cleaned.append(cid)
            seen.add(cid)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    return cleaned

# --- Step 1: Get or prompt for show IMDb ID (never for episode filenames) ---
def extract_years_from_folder(folder_name: str):
    """
    Return (start_year, end_year) if found in folder_name, else (None, None).
    Accepts forms like:
      - "Show Title (1982-1986)"
      - "Show Title 2008"
      - "Show Title (2008)"
      - "Show Title (1982–1986)"  (en-dash)
    """
    if not folder_name:
        return None, None
    # Normalize dashes
    name = folder_name.replace('\u2013', '-').replace('\u2014', '-')
    # Try parentheses first
    m = re.search(r'\((\d{4})(?:\s*-\s*(\d{4}))?\)', name)
    if m:
        start = m.group(1)
        end = m.group(2) or m.group(1)
        return start, end
    # Try standalone year or year-range without parentheses
    m = re.search(r'(?<!\d)(\d{4})(?:\s*-\s*(\d{4}))?(?!\d)', name)
    if m:
        start = m.group(1)
        end = m.group(2) or m.group(1)
        return start, end
    return None, None

# Helper: derive the series folder name from a file path or folder name
def get_series_folder_name(path_or_name):
    """
    If path_or_name is a Path object or a string representing a path, return the series folder name.
    If the immediate folder looks like a season folder (S01, Season 1, s1, etc.), return the parent folder name.
    Otherwise return the leaf folder name normalized (replace en-dash/em-dash).
    """
    # Normalize input to a name string
    name = None
    try:
        from pathlib import Path as _P
        if isinstance(path_or_name, _P):
            leaf = path_or_name.parent.name if path_or_name.is_file() else path_or_name.name
            name = leaf
            # If it's a season folder, take the parent folder
            if re.match(r'^(s\d+|season\s*\d+)$', name.strip(), re.I):
                gp = path_or_name.parent.parent
                if gp:
                    return str(gp.name).replace('\u2013', '-').replace('\u2014', '-').strip()
        else:
            name = str(path_or_name)
    except Exception:
        name = str(path_or_name)

    # If name looks like a season folder (e.g. "Season 01"), try to strip and return parent if path-like
    if re.match(r'^(s\d+|season\s*\d+)$', name.strip(), re.I):
        # Try to interpret as path and return grandparent if possible
        try:
            p = Path(name)
            gp = p.parent.parent
            if gp and gp.name:
                return gp.name.replace('\u2013', '-').replace('\u2014', '-').strip()
        except Exception:
            pass

    # Otherwise just normalize punctuation and return the leaf folder name
    return name.replace('\u2013', '-').replace('\u2014', '-').strip()


def get_or_prompt_show_imdb_id(show, folder_name, show_id_map):
    # Prompt handled by GUI module (imported above). The prompt function
    # signature matches the previous nested implementation and returns
    # None, a string imdb_id, or (imdb_id, True) when override chosen.
    """
    Resolve an IMDb ID for a show using (in order):
      1. cached show_id_map for this session
      2. imdb_cache.json (keyed by folder_name)
         - if found: compare media cache metadata years to folder_name years.
           * If years match (or folder has no year), accept cached id.
           * If mismatch, prompt user to accept cached ID or search for a different one.
      3. GUI search (get_series_imdb_id_gui)
    The selected imdb_id is saved into show_id_map[(show, cache_key)] and, when appropriate,
    into imdb_cache.json for future runs (except when user explicitly rejects saving).
    """
    # cache_key = folder_name or show
    series_folder_for_cache = get_series_folder_name(folder_name if not isinstance(folder_name, Path) else folder_name)
    cache_key = series_folder_for_cache or show
    if (show, cache_key) in show_id_map:
        try:
            cached = show_id_map[(show, cache_key)]
            debug_print(f"[DEBUG] Matched series metadata for {show} -> {cached} (from session cache)")
        except Exception:
            pass
        return show_id_map[(show, cache_key)]

    # Load imdb_cache
    imdb_cache = load_imdb_cache()

    from config import ui_debug_print
    ui_debug_print(f"[DBG] get_or_prompt_show_imdb_id: loaded imdb_cache keys={list(imdb_cache.keys())[:20]} (len={len(imdb_cache)}) for cache_key={cache_key!r}")

    # Normalize folder name for comparisons (replace en-dash etc)
    folder_norm = str(folder_name).replace('\u2013', '-').replace('\u2014', '-').strip() if folder_name else folder_name

    # First try the imdb_cache lookup using the folder-based key
    cached_imdb_id = imdb_cache.get(cache_key) or imdb_cache.get(folder_norm) or imdb_cache.get(show)
    cached_meta = get_entry(cached_imdb_id) if cached_imdb_id else None

    # If we have a cached imdb id but no metadata yet, fetch title/year now to populate media cache
    # This ensures fields like 'type' and 'totalSeasons' are present and avoids mis-classifying series
    if cached_imdb_id and (not cached_meta or not cached_meta.get('year')):
        try:
            debug_print(f"[DEBUG] Populating missing media metadata for cached IMDb ID {cached_imdb_id}...")
            # Populate metadata and episodes in one call where possible; avoid extra poster scraping here
            try: 
                from actions.omdb_gui_scraper import safe_request, fetch_title_and_year_from_imdb_id
                # Use safe_request when available so network/I/O runs off main thread
                safe_request(fetch_title_and_year_from_imdb_id, cached_imdb_id, True, False,
                             message=f"Fetching metadata and episodes for {cached_imdb_id}...")
            except Exception:
                # Fallback to synchronous call
                fetch_title_and_year_from_imdb_id(cached_imdb_id, populate_episodes=True, fetch_poster=False)
            cached_meta = get_entry(cached_imdb_id)
            ui_debug_print(f"[DBG] After population: cached_meta for {cached_imdb_id} = {('present' if cached_meta else 'MISSING')}")
        except Exception as e:
            debug_print(f"[WARN] Failed to populate metadata for {cached_imdb_id}: {e}")
        # If this turned out to be a series, try to populate episode map too.
        # Keep a generous safety cap to avoid hammering OMDb for extremely large series.
        try:
            if cached_meta and cached_meta.get('type') == 'series' and not cached_meta.get('episodes'):
                ts = cached_meta.get('totalSeasons')
                try:
                    tsn = int(ts) if ts is not None else None
                except Exception:
                    tsn = None
                # If totalSeasons unknown or reasonably small, populate episodes now
                if tsn is None or tsn <= 50:
                    debug_print(f"[DEBUG] Populating episode map for series {cached_imdb_id} (totalSeasons={ts})")
                    try:
                        # fetch_episode_ids_omdb will add episodes into media cache via add_episode_to_series
                        fetch_episode_ids_omdb(cached_imdb_id, {}, lambda: None)
                        cached_meta = get_entry(cached_imdb_id)
                    except Exception as e:
                        debug_print(f"[WARN] Failed to populate episode ids for {cached_imdb_id}: {e}")
                else:
                    debug_print(f"[INFO] Skipping episode population for {cached_imdb_id}: totalSeasons={tsn} exceeds safety threshold")
        except Exception:
            pass


    # If we have a cached imdb id from imdb_cache, validate its years against folder_name
    if cached_imdb_id and cached_meta:
        cached_type = cached_meta.get('type')
        folder_start, folder_end = extract_years_from_folder(folder_norm)
        meta_start = cached_meta.get('year')
        meta_end = cached_meta.get('end_year') or cached_meta.get('year')

        if meta_start:
            try:
                meta_start = str(meta_start)
            except Exception:
                pass
        if meta_end:
            try:
                meta_end = str(meta_end)
            except Exception:
                pass

        # If folder contains no year information and cached entry is a series, accept it
        if cached_type == 'series' and (not folder_start):
            imdb_id = cached_imdb_id
            debug_print(f"[DEBUG] Matched series metadata for {show} -> {imdb_id}")
            show_id_map[(show, cache_key)] = imdb_id
            return imdb_id

        # If folder has a year(s) and cached meta has year(s), compare using token rules
        if cached_type == 'series' and folder_start:
            # Normalize and compare year tokens. Rules:
            # - Replace hyphen variants with spaces and extract 4-digit year tokens.
            # - If either side is a single-year, accept if that year appears on the other side.
            # - If both sides are multi-year, accept only when the token sets are identical.
            def _tokens_from(start, end, raw_folder=None):
                # Build a combined string from start/end/raw_folder, normalize dashes to spaces
                pieces = []
                try:
                    if start is not None:
                        pieces.append(str(start))
                    if end is not None and str(end) != str(start):
                        pieces.append(str(end))
                except Exception:
                    pass
                if raw_folder:
                    pieces.append(str(raw_folder))
                s = " ".join(pieces)
                # normalize dash variants to spaces and extract 4-digit year tokens
                s = s.replace('\u2013', ' ').replace('\u2014', ' ').replace('-', ' ')
                import re as _re
                toks = _re.findall(r"\d{4}", s)
                # Filter to plausible years (1900-2099) and dedupe while preserving order
                out = []
                for t in toks:
                    try:
                        v = int(t)
                        if 1900 <= v <= 2099:
                            if t not in out:
                                out.append(t)
                    except Exception:
                        continue
                return out

            folder_tokens = _tokens_from(folder_start, folder_end, raw_folder=folder_norm)
            meta_tokens = _tokens_from(meta_start, meta_end, raw_folder=None)

            years_match = False
            try:
                if not folder_tokens or not meta_tokens:
                    years_match = False
                elif len(folder_tokens) == 1 or len(meta_tokens) == 1:
                    # If either side is a single year, accept if that year appears on the other side
                    years_match = bool(set(folder_tokens) & set(meta_tokens))
                else:
                    # Both are multi-year: require exact token set equality to match
                    years_match = set(folder_tokens) == set(meta_tokens)
            except Exception:
                years_match = False

            # If the cached ID is already used for a different folder with different years, never use it
            if not years_match:
                debug_print(f"⚠️ Not using cached IMDb ID {cached_imdb_id} for {cache_key}: years do not match. folder_tokens={folder_tokens} meta_tokens={meta_tokens}")
                ui_debug_print(f"[DBG] cache validation details: cache_key={cache_key!r} cached_imdb_id={cached_imdb_id} folder_tokens={folder_tokens} meta_tokens={meta_tokens}")
                cached_imdb_id = None
                cached_meta = None
                # Force prompt for new ID below
            else:
                imdb_id = cached_imdb_id
                debug_print(f"[DEBUG] Matched series metadata for {show} -> {imdb_id} (folder_tokens={folder_tokens} meta_tokens={meta_tokens})")
                show_id_map[(show, cache_key)] = imdb_id
                return imdb_id

    ui_debug_print(f"[DBG] get_or_prompt_show_imdb_id: after cache validation cached_imdb_id={cached_imdb_id} cached_meta={'yes' if cached_meta else 'no'}")

    # Before prompting, try to extract IMDb ID from folder name
    folder_imdb_id = get_folder_imdb_id(folder_name)
    if folder_imdb_id:
        meta = get_entry(folder_imdb_id)
        title_val = meta.get('title') if meta else None
        if title_val and title_val.strip().lower() == str(show).strip().lower():
            debug_print(f"[IMDB] Using IMDb ID from folder name: {folder_imdb_id} (title matches '{show}')")
            imdb_cache[cache_key] = folder_imdb_id
            try:
                save_imdb_cache(imdb_cache)
            except Exception:
                pass
            debug_print(f"[DEBUG] Matched series metadata for {show} -> {folder_imdb_id}")
            show_id_map[(show, cache_key)] = folder_imdb_id
            return folder_imdb_id
        else:
            debug_print(f"[IMDB] Folder contains IMDb ID '{folder_imdb_id}', but title does not match ('{meta.get('title') if meta else None}' vs '{show}'). Prompting user.")

    # If cached_imdb_id is not present or not acceptable, fall back to GUI search
    while True:
        ui_debug_print(f"[DBG] get_or_prompt_show_imdb_id: no usable imdb_cache entry, prompting GUI for {cache_key}")
        imdb_id = get_series_imdb_id_gui(cache_key, search_title=show)
        ui_debug_print(f"[DBG] get_or_prompt_show_imdb_id: GUI returned imdb_id={imdb_id}")
        if imdb_id is None:
            debug_print(f"⏭️ Skipped by user: {cache_key}")
            return None

        meta = get_entry(imdb_id) if imdb_id else None
        # If this is a newly-picked series (no metadata or no episodes), try to populate metadata and episodes now.
        if not meta or not meta.get('episodes'):
            try:
                # populate_episodes=True will fetch season data (bounded by totalSeasons)
                from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id, safe_request
                ui_debug_print(f"[DBG] get_or_prompt_show_imdb_id: fetching title/year for newly-picked imdb_id={imdb_id} (populate_episodes=True)")
                try:
                    safe_request(fetch_title_and_year_from_imdb_id, imdb_id, True, False,
                                 message=f"Fetching metadata and episodes for {imdb_id}...")
                except Exception:
                    # fallback to direct call if safe_request misbehaves
                    fetch_title_and_year_from_imdb_id(imdb_id, populate_episodes=True, fetch_poster=False)
            except Exception:
                # best-effort only; if this fails we'll fall back to the missing-episodes prompt later
                pass
            # refresh meta after attempted population
            meta = get_entry(imdb_id) if imdb_id else None
        ui_debug_print(f"[DBG] get_or_prompt_show_imdb_id: post-population meta={'present' if meta else 'MISSING'} for imdb_id={imdb_id}")
        folder_start, folder_end = extract_years_from_folder(cache_key)

        def imdb_id_used_for_other_series(imdb_id, cache_key, folder_start, folder_end):
            for k, v in imdb_cache.items():
                if k != cache_key and v == imdb_id:
                    other_start, other_end = extract_years_from_folder(k)
                    if (other_start != folder_start) or (other_end != folder_end):
                        return True
            return False

        # If the picked ID is already used for a different folder with different years, show dialog
        if meta and meta.get('type') == 'series' and imdb_id_used_for_other_series(imdb_id, cache_key, folder_start, folder_end):
            reason = f"The IMDb ID you selected is already used for another folder with different years. Please enter a valid IMDb ID for this folder or skip."
            manual_id = prompt_for_imdb_id_conflict(folder_name, imdb_id, reason)
            ui_debug_print(f"[DBG] imdb_conflict_prompt returned: {manual_id} (type={type(manual_id)}) for {cache_key}")
            if manual_id is None:
                debug_print(f"⏭️ Skipped by user: {cache_key}")
                return None
            # prompt may return (imdb_id, override_flag) when the user pressed the override button
            if isinstance(manual_id, tuple):
                imdb_id, force_override = manual_id
            else:
                imdb_id = manual_id
                force_override = False
            meta = get_entry(imdb_id) if imdb_id else None
            # Re-check for conflict unless the user explicitly chose to override for this folder
            if imdb_id_used_for_other_series(imdb_id, cache_key, folder_start, folder_end) and not force_override:
                continue
        
        def is_ambiguous_season_folder(key):
            import re
            season_patterns = [r'^(s\d+)$', r'^(S\d+)$', r'^(season \d+)$', r'^(Season \d+)$']
            for pat in season_patterns:
                if re.match(pat, (key or "").strip()):
                    return True
            return False

        if meta and meta.get('type') == 'series' and not is_ambiguous_season_folder(cache_key):
            try:
                imdb_cache[cache_key] = imdb_id
                save_imdb_cache(imdb_cache)
            except Exception:
                pass
            # We've accepted this IMDb ID for this folder — store in session map and return
            # Historical note / why this exists:
            # Previously this branch only saved the imdb mapping into the on-disk
            # `imdb_cache` and continued the loop without returning. That caused
            # two problems during the "cold" path:
            #  1) The while-loop would re-prompt immediately and appear to repeat
            #     indefinitely (the caller re-entered the GUI picker repeatedly).
            #  2) We also had nested calls to `safe_request` (safe_request -> worker
            #     thread -> fetch_episode_ids_omdb -> safe_request), which attempted
            #     to access the Tk root from a non-main thread (get_root enforces
            #     main-thread access) and raised a runtime error. To avoid both
            #     issues we now (a) return immediately after accepting the user's
            #     selection so the prompt loop ends, and (b) ensure internal helpers
            #     like `fetch_episode_ids_omdb` do not call UI-affecting helpers
            #     (e.g. do not call safe_request themselves) to prevent nested UI
            #     access from worker threads.
            debug_print(f"[DEBUG] Matched series metadata for {show} -> {imdb_id}")
            show_id_map[(show, cache_key)] = imdb_id
            return imdb_id

    # debug_print(f"[DEBUG] Matched series metadata for {show} -> {imdb_id}")
    # show_id_map[(show, cache_key)] = imdb_id
    # return imdb_id

# --- Step 2: Lookup episode IMDb ID (media_metadata is canonical) ---
def lookup_episode_id(imdb_id, season, episode, file_stem=None):
    episode_nums = _episode_numbers(episode)
    if len(episode_nums) > 1:
        resolved = []
        for ep_num in episode_nums:
            ep_id = lookup_episode_id(imdb_id, season, ep_num, file_stem=None)
            if not ep_id:
                return None
            resolved.append(ep_id)
        return resolved

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
        meta = get_entry(imdb_id) if imdb_id else None
        if meta and 'episodes' in meta:
            for s, eps in meta['episodes'].items():
                for ep_num, ep_id in eps.items():
                    if str(ep_num) == str(episode):
                        return ep_id
    return None

# --- Step 3: Get or prompt for episode IMDb ID (never pollute imdb_cache.json) ---
def get_episode_imdb_id(show, imdb_id, season, episode, file_stem=None):
    episode_nums = _episode_numbers(episode)
    if len(episode_nums) > 1:
        ep_ids = lookup_episode_id(imdb_id, season, episode, file_stem=None)
        if ep_ids:
            return ep_ids
        if imdb_id:
            fetch_episode_ids_omdb(imdb_id, {}, lambda: None)
        ep_ids = lookup_episode_id(imdb_id, season, episode, file_stem=None)
        if ep_ids:
            return ep_ids

        collected = []
        manual_episode_cache = load_manual_episode_cache()
        for ep_num in episode_nums:
            prompt_title = f"{show} {_format_episode_label(season, ep_num)}"
            prompt_msg = f"Enter IMDb episode ID for: {prompt_title}"
            ep_single = prompt_for_episode_id(prompt_title, prompt_msg)
            if not ep_single:
                return None
            manual_episode_cache.setdefault(str(imdb_id), {}).setdefault(str(season), {})[str(ep_num)] = ep_single
            collected.append(ep_single)
        save_manual_episode_cache(manual_episode_cache)

        if file_stem and collected:
            manual_title_cache = load_manual_episode_title_cache()
            manual_title_cache[file_stem] = "|".join(collected)
            save_manual_episode_title_cache(manual_title_cache)
        return collected

    ep_id = lookup_episode_id(imdb_id, season, episode, file_stem=file_stem)
    if ep_id:
        return ep_id
    if imdb_id:
        fetch_episode_ids_omdb(imdb_id, {}, lambda: None)
    ep_id = lookup_episode_id(imdb_id, season, episode, file_stem=file_stem)
    if ep_id:
        return ep_id
    if season is not None and episode is not None:
        prompt_title = f"{show} {_format_episode_label(season, episode)}"
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
        meta = get_entry(imdb_id) if imdb_id else None
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

    input_episode_nums = _episode_numbers(episode)
    manual_slot_locked = False

    # Canonical episode info from metadata
    override_season, override_episode = season, episode
    episode_ids = _episode_id_list(ep_id)
    primary_ep_id = episode_ids[0] if episode_ids else None

    # If this file/slot resolves via manual season remap, preserve local parsed numbering.
    # Otherwise, canonical metadata may overwrite local episode indices and cause shifted labels.
    try:
        if imdb_id and season is not None and len(input_episode_nums) == 1 and primary_ep_id:
            manual_episode_cache = load_manual_episode_cache()
            mapped = (
                manual_episode_cache
                .get(str(imdb_id), {})
                .get(str(season), {})
                .get(str(input_episode_nums[0]))
            )
            if mapped and str(mapped) == str(primary_ep_id):
                manual_slot_locked = True
    except Exception:
        manual_slot_locked = False

    ep_info = get_episode_info_by_id(primary_ep_id) if primary_ep_id else None
    from core.series_utils import get_episode_title_from_cache
    canonical_ep_title = get_episode_title_from_cache(primary_ep_id) if primary_ep_id else None
    if len(input_episode_nums) > 1:
        canonical_ep_title = None
    # Debug: if the episode title contains dots (e.g. acronyms like "L.A. Story")
    # or if this is the known problematic episode, log extras handling to help debug
    try:
        if (isinstance(canonical_ep_title, str) and '.' in canonical_ep_title): #or primary_ep_id == 'tt34929210':
            #debug_print(f"[DBG] build_episode_path: ep_id={ep_id} canonical_ep_title={repr(canonical_ep_title)} extras_in={repr(extras)}")
            pass
    except Exception:
        pass
    is_movie_cut_special = False
    if ep_info:
        # If OMDb type is 'movie' but we're in a series context, treat as special
        if ep_info.get('type') == 'movie' and imdb_id:
            override_season = 0
            override_episode = 0
            is_movie_cut_special = True
        if ep_info.get('season') is not None and len(input_episode_nums) <= 1 and not manual_slot_locked:
            try:
                override_season = int(ep_info['season'])
            except Exception:
                override_season = ep_info['season']
        if ep_info.get('episode') is not None and len(input_episode_nums) <= 1 and not manual_slot_locked:
            try:
                override_episode = int(ep_info['episode'])
            except Exception:
                override_episode = ep_info['episode']
        if ep_info.get('series_title'):
            series_title = ep_info['series_title']

    # Build extras (deduplicate, always include non-canonical info)
    from config import PREPEND_EPISODE_TITLE_TO_EXTRAS
    extras_out = []

    # Normalize 'extras' into iterable tokens
    if extras:
        # if extras is a string, keep it as a single token; if list/tuple/set, extend
        if isinstance(extras, (list, tuple, set)):
            for x in extras:
                if x:
                    extras_out.append(str(x))
        else:
            extras_out.append(str(extras))

    # Prepend or replace episode title in extras robustly
    if PREPEND_EPISODE_TITLE_TO_EXTRAS and canonical_ep_title:
        # import re
        # def normalize_title(title):
        #     title = title.lower()
        #     title = re.sub(r"[.,'’\"!?;:\-\(\)\[\]]", "", title)
        #     title = title.replace("&", "and")
        #     title = re.sub(r"\s+", " ", title)
        #     return title.strip()
        import re, unicodedata
        def normalize_title(title):
            if title is None:
                return ""
            title = unicodedata.normalize("NFKD", str(title))
            # map dash variants to ASCII hyphen
            title = re.sub(r"[‐-‒–—―]", "-", title)
            title = title.replace("&", "and")
            # replace dots with spaces for acronyms (B.U.D.D.Y. -> B U D D Y)
            title = re.sub(r"\.", " ", title)
            # remove ! and ? (treat as equivalent to nothing)
            title = title.replace("!", "").replace("?", "")
            # remove punctuation but keep spaces and hyphens
            title = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
            # replace hyphens with spaces so "Ice-Ca" and "Ice Ca" compare equal
            title = title.replace("-", " ")
            # collapse multiple spaces
            title = re.sub(r"\s+", " ", title).strip().lower()
            return title

        def collapse_spaces(s):
            return re.sub(r"\s+", "", s or "")
        

        def levenshtein(a, b):
            if a == b:
                return 0
            if not a:
                return len(b)
            if not b:
                return len(a)
            prev_row = list(range(len(b) + 1))
            for i, ca in enumerate(a, 1):
                curr_row = [i]
                for j, cb in enumerate(b, 1):
                    insertions = prev_row[j] + 1
                    deletions = curr_row[j - 1] + 1
                    substitutions = prev_row[j - 1] + (ca != cb)
                    curr_row.append(min(insertions, deletions, substitutions))
                prev_row = curr_row
            return prev_row[-1]

        title_str = str(canonical_ep_title).strip()
        norm_canonical = normalize_title(title_str)
        
        new_extras_out = []
        for e in extras_out:
            e_clean = str(e).strip()
            if not e_clean:
                continue
            # Targeted debug for titles with dots or specific problematic ep_id
            dbg_trace = ('.' in title_str) #or (primary_ep_id in ('tt34929210', 'tt9313942', 'tt5582700'))  
            # Try substring match with normalized comparison
            extras_words = e_clean.split()
            match = None
            for i in range(len(extras_words)):
                for j in range(i+1, len(extras_words)+1):
                    candidate = " ".join(extras_words[i:j])
                    norm_candidate = normalize_title(candidate)
                    if dbg_trace:
                        pass
                        #debug_print(f"[DBG-match] ep_id={ep_id} candidate='{candidate}' norm_candidate='{norm_candidate}' norm_canonical='{norm_canonical}'")
                    # Exact normalized match or match after collapsing spaces (to catch 'What Ever' vs 'Whatever')
                    if norm_candidate == norm_canonical or collapse_spaces(norm_candidate) == collapse_spaces(norm_canonical):
                        match = candidate
                        break
                if match:
                    break
            if match:
                # Build a whitespace-flexible regex so we match regardless of single vs multiple spaces
                # Use whitespace-flexible pattern and allow matches at whitespace/string boundaries
                ws_pattern = r"(?<!\S)" + r"\s+".join([re.escape(tok) for tok in match.split()]) + r"(?!\S)"
                pattern = re.compile(ws_pattern, flags=re.IGNORECASE)
                replaced = pattern.sub(title_str, e_clean, count=1).strip()
                if dbg_trace:
                    #debug_print(f"[DBG-replace] ep_id={ep_id} match='{match}' replaced='{replaced}' title_str='{title_str}' e_clean='{e_clean}'")
                    pass
                if normalize_title(replaced) == norm_canonical:
                    new_extras_out.append(title_str)
                else:
                    new_extras_out.append(replaced)
            else:
                norm_e = normalize_title(e_clean)
                # Also compare with all spaces removed to catch 'Whatever' vs 'What Ever'
                if collapse_spaces(norm_e) == collapse_spaces(norm_canonical):
                    new_extras_out.append(title_str)
                else:
                    distance = levenshtein(norm_e, norm_canonical)
                    if distance <= 2:
                        new_extras_out.append(title_str)
                    else:
                        new_extras_out.append(f"{title_str} - {e_clean}")

        # Deduplicate based on normalized form
        extras_out = []
        seen_norms = set()
        for block in new_extras_out:
            if not block:
                continue
            token = str(block).strip()
            if not token:
                continue
            norm = normalize_title(token)
            if norm not in seen_norms:
                extras_out.append(token)
                seen_norms.add(norm)
        # if ('tt9313942' == ep_id) or dbg_trace:
        #     debug_print(f"[DBG-final-extras] ep_id={ep_id} new_extras_out={new_extras_out} extras_out={extras_out}")

    # For edge/specials or movie-cut specials, always include original file stem as extra
    if (season is None or episode is None or is_movie_cut_special) and original_file_stem:
        extras_out.append(original_file_stem)
        if is_movie_cut_special:
            extras_out.append("Movie Cut")

    # Remove duplicates and empty extras while preserving order
    seen = set()
    deduped_extras = []
    for e in extras_out:
        if not e:
            continue
        token = str(e).strip()
        if not token:
            continue
        if token not in seen:
            deduped_extras.append(token)
            seen.add(token)

    # Compose filename
    if override_season is not None and override_episode is not None:
        try:
            s_num = int(override_season)
            episode_nums = _episode_numbers(override_episode)
            if not episode_nums:
                episode_nums = _episode_numbers(episode)
            if s_num == 0:
                season_folder = "Season 00"
            else:
                season_folder = f"Season {s_num:02}"
            if len(episode_nums) > 1:
                episode_code = f"S{s_num:02}E{episode_nums[0]:02}" + "".join([f"-E{n:02}" for n in episode_nums[1:]])
            elif len(episode_nums) == 1:
                episode_code = f"S{s_num:02}E{episode_nums[0]:02}"
            else:
                episode_code = "S00E00"
            episode_name = f"{series_title} - {episode_code}"
        except Exception:
            # fallback if season/episode aren't integers
            season_folder = "Season 00"
            episode_name = f"{series_title} - S00E00"
    else:
        season_folder = "Season 00"
        episode_name = f"{series_title} - S00E00"

    # Add extras if any
    if deduped_extras:
        extras_str = " - ".join([e for e in deduped_extras if e])
        if extras_str and extras_str not in episode_name:
            episode_name += f" [{extras_str}]"

    # Always append episode IMDb ID
    for eid in episode_ids:
        cleaned_ep_id = clean_brackets(eid)
        if cleaned_ep_id and cleaned_ep_id not in episode_name:
            episode_name += f" [{cleaned_ep_id}]"

    # Compose show folder name with years and IMDb ID
    # Collapse any accidental multiple spaces introduced during replacements
    try:
        episode_name = re.sub(r"\s{2,}", " ", episode_name)
    except Exception:
        pass
    # Post-process punctuation artifacts introduced during extras/title merging:
    # - collapse duplicate hyphen groups (" - - " -> " - ")
    # - convert patterns like " -!" or "- !" to just a single exclamation mark
    # - collapse repeated punctuation separated by spaces ("! !" -> "!")
    #   but preserve intentional double-exclamation marks if present in canonical episode title
    try:
        # Collapse repeated hyphens into a single spaced hyphen
        episode_name = re.sub(r"\s*-\s*-\s*", " - ", episode_name)

        # If we have patterns like "-!" (possibly with surrounding spaces), remove the hyphen
        episode_name = re.sub(r"\s*-\s*!", " !", episode_name)

        # Collapse repeated punctuation (!, ?, .) when repeated with optional spaces: "! !" -> "!"
        # Preserve intentional '!!' occurrences if the canonical episode title contains '!!'
        def _collapse_punct(m):
            ch = m.group(1)
            seq = m.group(0)
            # Count how many punctuation characters are present in the matched sequence (ignore spaces)
            try:
                repeats = len(re.sub(r"\s+", "", seq))
            except Exception:
                repeats = 1
            # If canonical episode title contains a run of repeated punctuation (e.g. '..' or '...')
            # preserve that run length. Otherwise collapse to a single punctuation char.
            try:
                cp = str(canonical_ep_title) if canonical_ep_title else ''
                runs = [len(mo.group(0)) for mo in re.finditer(rf"\{ch}+", cp)]
                max_run = max(runs) if runs else 0
            except Exception:
                max_run = 0
            if max_run >= 2:
                # Preserve the canonical run length (e.g., '!!' or '...')
                return ch * max_run
            # If canonical doesn't specify a run, collapse to a single punctuation mark
            return ch

        episode_name = re.sub(r'([!?.])(?:\s*\1)+', lambda m: _collapse_punct(m), episode_name)

        # Final collapse of accidental multiple spaces that may have been reintroduced
        episode_name = re.sub(r"\s{2,}", " ", episode_name)
        # Trim stray spaces before closing bracket(s)
        episode_name = re.sub(r"\s+\]", "]", episode_name)
        # Trim stray spaces after opening bracket(s)
        episode_name = re.sub(r"\[\s+", "[", episode_name)
    except Exception:
        pass
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

    # --- Load imdb_cache helper ---
    import json
    imdb_cache_path = Path(__file__).parent.parent / 'cache' / 'imdb_cache.json'
    def load_imdb_cache():
        try:
            with open(imdb_cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    def save_imdb_cache(cache):
        """
        Save the imdb_cache to disk in a background thread to avoid blocking the GUI.
        Writes to a temporary file and atomically replaces the target file.
        """
        import threading, os

        def _writer(data):
            try:
                tmp_path = imdb_cache_path.with_suffix('.tmp')
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                try:
                    os.replace(tmp_path, imdb_cache_path)
                except Exception:
                    # fallback to rename
                    try:
                        tmp_path.rename(imdb_cache_path)
                    except Exception:
                        pass
            except Exception:
                # best effort only
                pass

        try:
            t = threading.Thread(target=_writer, args=(cache,), daemon=True)
            t.start()
        except Exception:
            # fallback to synchronous write if thread spawn fails
            try:
                with open(imdb_cache_path, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    imdb_cache = load_imdb_cache()

    # --- Helpers for grouping and normalization ---
    def normalize_folder_name(name: str) -> str:
        # Normalize unicode punctuation differences (e.g. en-dash vs hyphen)
        if not name:
            return name
        return name.replace('\u2013', '-').replace('\u2014', '-').strip()

    def get_canonical_group_key(show, folder_name):
        """Return a grouping key for files that belong to the same logical show+years group.

        The function prefers an IMDb id found in the folder name. If not found, it falls back
        to using cached imdb_cache or prompting the user. If folder years and metadata years
        disagree, it uses a folder-years-specific key to avoid mixing distinct runs.
        """
        folder_name_norm = normalize_folder_name(folder_name)
        folder_start, folder_end = extract_years_from_folder(folder_name_norm)

        # If folder explicitly contains an IMDb id (preferred), use that to build unique group key.
        folder_imdb_id = get_folder_imdb_id(folder_name_norm)
        if folder_imdb_id:
            meta = get_entry(folder_imdb_id)
            if meta and meta.get('title'):
                series_title = meta['title']
                start_year = meta.get('year')
                end_year = meta.get('end_year')
                years_str = ""
                try:
                    if start_year:
                        start_year = str(start_year)
                    if end_year:
                        end_year = str(end_year)
                except Exception:
                    pass
                if start_year and end_year and start_year != end_year:
                    years_str = f" ({start_year}-{end_year})"
                elif start_year:
                    years_str = f" ({start_year})"
                debug_print(f"[DEBUG] Matched series metadata for {show} -> {folder_imdb_id} (from folder name)")
                return f"{series_title}{years_str} [{folder_imdb_id}]"
            return f"{show} [{folder_imdb_id}]"

        # No folder imdb id — fall back to prompting / imdb cache via folder name.
        imdb_id = get_or_prompt_show_imdb_id(show, folder_name_norm, show_id_map)
        meta = get_entry(imdb_id) if imdb_id else None
        meta_start = meta.get('year') if meta else None
        meta_end = meta.get('end_year') if meta else None
        # Normalize to string
        if meta_start:
            try:
                meta_start = str(meta_start)
            except Exception:
                pass
        if meta_end:
            try:
                meta_end = str(meta_end)
            except Exception:
                pass

        # If folder has year(s), and metadata has year(s), and they do not match, force a unique group key and prompt for new ID
        # Use the same token-normalization/matching rules as get_or_prompt_show_imdb_id
        def _tok(start, end, raw=None):
            pieces = []
            try:
                if start is not None:
                    pieces.append(str(start))
                if end is not None and str(end) != str(start):
                    pieces.append(str(end))
            except Exception:
                pass
            if raw:
                pieces.append(str(raw))
            s = " ".join(pieces)
            s = s.replace('\u2013', ' ').replace('\u2014', ' ').replace('-', ' ')
            import re as _re
            toks = _re.findall(r"\d{4}", s)
            # Filter to plausible years and dedupe
            seen = set(); res = []
            for t in toks:
                try:
                    v = int(t)
                    if 1900 <= v <= 2099 and t not in seen:
                        res.append(t); seen.add(t)
                except Exception:
                    continue
            return res

        folder_tokens = _tok(folder_start, folder_end, raw=folder_name_norm)
        meta_tokens = _tok(meta_start, meta_end, raw=meta_start)
        years_mismatch = False
        try:
            if not folder_tokens or not meta_tokens:
                years_mismatch = False
            elif len(folder_tokens) == 1 or len(meta_tokens) == 1:
                years_mismatch = not bool(set(folder_tokens) & set(meta_tokens))
            else:
                # both multi-year: require exact token equality
                years_mismatch = set(folder_tokens) != set(meta_tokens)
        except Exception:
            years_mismatch = False

        if meta and meta.get('title') and not years_mismatch:
            series_title = meta['title']
            start_year = meta.get('year')
            end_year = meta.get('end_year')
            years_str = ""
            try:
                if start_year:
                    start_year = str(start_year)
                if end_year:
                    end_year = str(end_year)
            except Exception:
                pass
            if start_year and end_year and start_year != end_year:
                years_str = f" ({start_year}-{end_year})"
            elif start_year:
                years_str = f" ({start_year})"
            return f"{series_title}{years_str} [{imdb_id}]"

        # If years mismatch, use folder's years in group key and force prompt for new ID
        if years_mismatch:
            years_str = ""
            if folder_start and folder_end and folder_start != folder_end:
                years_str = f" ({folder_start}-{folder_end})"
            elif folder_start:
                years_str = f" ({folder_start})"
            return f"{show}{years_str} [FOLDER-YEARS]"

        # Last fallback: keep folder_name in the group key so similarly named titles in different folders don't merge accidentally.
        return f"{show} [{folder_name_norm}]"

    # Build grouping: key = canonical title + years
    series_files = {}
    for file in SERIES_DIR.rglob("*"):
        if not (file.is_file() and is_video_file(file)):
            continue
        show, season, episode, extras = extract_episode_info(file.stem)
        folder_name = get_series_folder_name(file)
        group_key = get_canonical_group_key(show, folder_name)
        series_files.setdefault(group_key, []).append(file)

    # Helper to process each group of files (keeps original behaviour but split for clarity)
    def process_group(group_key, files):
        debug_print(f"Processing group: {group_key}")
        first_file = files[0]
        show, season, episode, extras = extract_episode_info(first_file.stem)
        folder_name = get_series_folder_name(first_file)
        imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
        folder_imdb_id = get_folder_imdb_id(folder_name)

        # If folder IMDb ID is in skip list, add missing episode IDs but skip renaming
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
                if not show:
                    continue
                ep_imdb_id = _get_episode_ids_from_filename(file.stem)
                if ep_imdb_id and _has_skipped_episode_id(ep_imdb_id, file.name):
                    debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_imdb_id})")
                    continue
                imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
                if imdb_id is None:
                    debug_print(f"⏭️ Skipped by user: {file.name}")
                    continue
                ep_id = ep_imdb_id if ep_imdb_id else get_episode_imdb_id(show, imdb_id, season, episode, file_stem=file.stem)
                if ep_id and _has_skipped_episode_id(ep_id, file.name):
                    debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_id})")
                    continue
                if folder_imdb_id and season and episode:
                    ep_id = lookup_episode_id(folder_imdb_id, season, episode)
                    debug_print(f"  lookup_episode_id result: {ep_id}")
                    if ep_id:
                        debug_print(f"Adding missing episode ID to: {file.name}")
                        id_suffix = "".join([f"[{eid}]" for eid in _episode_id_list(ep_id)])
                        new_stem = file.stem + id_suffix
                        new_path = file.parent / (new_stem + file.suffix)
                        shutil.move(str(file), str(new_path))
                        # Avoid planning a no-op (src == dest)
                        try:
                            if Path(str(file)).resolve() == Path(new_path).resolve():
                                #debug_print(f"[DEBUG] Skipping plan entry (no change): {file} -> {new_path}")
                                pass
                            else:
                                planned.append({
                                    "type": "Series",
                                    "src": str(file),
                                    "dest": str(new_path)
                                })
                                debug_print(f"Planned ADD ONLY IMDb ID for skipped folder: {file.name} -> {new_path}")
                        except Exception:
                            # resolution failed; append as fallback
                            planned.append({
                                "type": "Series",
                                "src": str(file),
                                "dest": str(new_path)
                            })
                            debug_print(f"Planned ADD ONLY IMDb ID for skipped folder: {file.name} -> {new_path}")
                else:
                    debug_print(f"No season/episode info for: {file.name}")
            return

        # Regular processing for files not in skip list
        for file in files:
            debug_print(f"  Processing file: {file.name}")
            show, season, episode, extras = extract_episode_info(file.stem)
            if not show:
                continue
            ep_imdb_id = _get_episode_ids_from_filename(file.stem)
            if ep_imdb_id and _has_skipped_episode_id(ep_imdb_id, file.name):
                debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_imdb_id})")
                continue
            imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
            if imdb_id is None:
                debug_print(f"⏭️ Skipped by user: {file.name}")
                continue
            ep_id = get_episode_imdb_id(show, imdb_id, season, episode)
            if ep_id and _has_skipped_episode_id(ep_id, file.name):
                debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_id})")
                continue
            fetch_episode_ids_omdb(imdb_id, {}, lambda: None)
            _, dest_path = build_episode_path(file, show, season, episode, extras, imdb_id, ep_id)
            try:
                if file.resolve() == dest_path.resolve():
                    debug_print(f"⏭️ Skipping (already correctly named): {file.relative_to(SERIES_DIR)}")
                    continue
            except Exception:
                if str(file) == str(dest_path):
                    debug_print(f"⏭️ Skipping (already correctly named by string match): {file}")
                    continue
            # Avoid adding no-op planned renames
            try:
                if Path(str(file)).resolve() == Path(dest_path).resolve():
                    #debug_print(f"[DEBUG] Skipping plan entry (no change): {file} -> {dest_path}")
                    continue
            except Exception:
                pass
            planned.append({
                "type": "Series",
                "src": str(file),
                "dest": str(dest_path)
            })
            debug_print(f"Planned FULL RENAME: {file.name} -> {dest_path}")

    # Process each group with the helper above
    for group_key, files in series_files.items():
        process_group(group_key, files)

    # Persist any changes to imdb_cache
    try:
        save_imdb_cache(imdb_cache)
    except Exception:
        pass


# --- Step 7: Rename (move) a single series file and its subtitles ---
def organize_series(preview_only: bool, selected_files=None):
    """Walk SERIES_DIR and rename/move each file in place.

    This mirrors the behaviour used by the planning function but performs actual moves.
    selected_files may be provided to only operate on a subset.
    """
    show_id_map = {}

    try:
        for file in SERIES_DIR.rglob("*"):
            # Skip non-video files and support filtered selections
            if not (file.is_file() and is_video_file(file)):
                continue
            if selected_files and str(file) not in selected_files:
                continue

            # Extract episode components from the filename
            show, season, episode, extras = extract_episode_info(file.stem)
            if not show:
                debug_print(f"❌ Skipping (unparsed): {file.name}")
                continue

            # Resolve show IMDb ID (may prompt user)
            imdb_id = get_or_prompt_show_imdb_id(show, file.parent.name, show_id_map)

            # Determine episode IMDb ID (could be embedded in filename or resolved via cache/prompts)
            ep_imdb_id = _get_episode_ids_from_filename(file.stem)
            ep_id = ep_imdb_id if ep_imdb_id else get_episode_imdb_id(show, imdb_id, season, episode, file_stem=file.stem)
            if ep_id and _has_skipped_episode_id(ep_id, file.name):
                debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_id})")
                continue

            # Build destination path using canonical metadata
            dest_folder, dest_path = build_episode_path(file, show, season, episode, extras, imdb_id, ep_id, original_file_stem=file.stem)

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
    """Plan renames but prompt via GUI for missing episode IMDb IDs.

    This function groups files by show+folder, fetches episode data from OMDb for known
    shows, and opens a batch dialog to collect missing episode IDs when needed.
    """
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

    # Collect all files by (show, folder_name)
    for file in SERIES_DIR.rglob("*"):
        if not (file.is_file() and is_video_file(file)):
            continue
        show, season, episode, extras = extract_episode_info(file.stem)
        if not show:
            continue
        folder_name = get_series_folder_name(file)
        show_files.setdefault((show, folder_name), []).append((file, season, episode, extras))

    # For each show, resolve a validated IMDb ID (this will consult imdb_cache but
    # also validate years and prompt the user if necessary). We intentionally call
    # get_or_prompt_show_imdb_id so mismatched-year cached entries do not get used
    # silently (this was the source of the missing conflict prompt).
    for (show, folder_name), files in show_files.items():
        imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
        if not imdb_id:
            debug_print(f"⏭️ Skipped fetching OMDb data for show: {show} (no IMDb ID)")
            continue
        # If this imdb_id appears to come from the imdb_cache, log which key matched
        try:
            cached_key = None
            for k, v in imdb_cache.items():
                if v == imdb_id:
                    cached_key = k
                    break
            if cached_key:
                debug_print(f"[DEBUG] Matched series metadata for {show} -> {imdb_id} (from imdb_cache key: {cached_key})")
        except Exception:
            pass

        # Build an episode_cache from media metadata (if present) so we only request missing seasons from OMDb
        from core.media_metadata_cache import get_entry
        episode_cache = {}
        meta = get_entry(imdb_id) if imdb_id else None
        if meta and 'episodes' in meta:
            try:
                for season_str, eps in meta['episodes'].items():
                    try:
                        s_num = int(season_str)
                    except Exception:
                        continue
                    episode_cache.setdefault(imdb_id, {})[s_num] = {}
                    for ep_str, epdata in eps.items():
                        try:
                            e_num = int(ep_str)
                        except Exception:
                            continue
                        if isinstance(epdata, dict):
                            eid = epdata.get('imdb_id') or epdata.get('imdbID') or epdata.get('id')
                        else:
                            eid = str(epdata) if epdata else None
                        if eid and eid != 'N/A':
                            episode_cache[imdb_id].setdefault(s_num, {})[e_num] = eid
            except Exception:
                # If any oddity occurs reading the cache, fall back to empty episode_cache
                episode_cache = {}

        # Check for missing episodes
        missing_episodes = []
        episode_map = {}
        for file, season, episode, extras in files:
            ep_id = None
            if file.stem in manual_title_cache:
                cached = manual_title_cache[file.stem]
                cached_ids = _episode_id_list(cached)
                if len(cached_ids) > 1:
                    ep_id = cached_ids
                else:
                    ep_id = cached
            elif season is not None and episode is not None:
                ep_id = lookup_episode_id(imdb_id, season, episode)
            if not ep_id:
                missing_episodes.append((file, season, episode, extras))
            else:
                episode_map[(season, episode)] = ep_id

        # Batch prompt for missing episode IDs using the GUI prompt component
        if missing_episodes:
            def on_submit(epid_map):
                manual_episode_cache = load_manual_episode_cache()
                for idx, (file, season, episode, extras) in enumerate(missing_episodes):
                    key = f"{_format_episode_label(season, episode)}: {file.name}"
                    ep_id = epid_map.get(key, "")
                    if ep_id and imdb_id:
                        parsed_ids = []
                        try:
                            parsed_ids = re.findall(r"tt\d{7,9}", str(ep_id))
                        except Exception:
                            parsed_ids = []
                        if not parsed_ids:
                            parsed_ids = [str(ep_id)]

                        episode_nums = _episode_numbers(episode)
                        if len(episode_nums) > 1 and len(parsed_ids) > 1:
                            for i, ep_num in enumerate(episode_nums):
                                if i < len(parsed_ids):
                                    manual_episode_cache.setdefault(str(imdb_id), {}).setdefault(str(season), {})[str(ep_num)] = parsed_ids[i]
                        elif len(episode_nums) > 1 and len(parsed_ids) == 1:
                            for ep_num in episode_nums:
                                manual_episode_cache.setdefault(str(imdb_id), {}).setdefault(str(season), {})[str(ep_num)] = parsed_ids[0]
                        else:
                            manual_episode_cache.setdefault(str(imdb_id), {}).setdefault(str(season), {})[str(episode)] = parsed_ids[0]
                        save_manual_episode_cache(manual_episode_cache)
                    manual_title_cache = load_manual_episode_title_cache()
                    if file.stem and ep_id:
                        manual_title_cache[file.stem] = ep_id
                        save_manual_episode_title_cache(manual_title_cache)
                # If called with a hidden root (CLI), quit it; otherwise the caller handles continuation
                try:
                    if root is not None and not hasattr(root, 'show_screen'):
                        root.quit()
                except Exception:
                    pass

            prompt_list = [f"{_format_episode_label(season, episode)}: {file.name}" for (file, season, episode, extras) in missing_episodes]
            # If running inside AppRoot (GUI mode), show a frame-based prompt and wait on a root-owned variable.
            if root is not None and hasattr(root, 'show_screen'):
                try:
                    done_var = tk.BooleanVar(root)
                    result_container = {}

                    def _on_submit_frame(mapping):
                        # Convert list-style mapping expected by frame to epid_map format
                        result_container.update(mapping)
                        done_var.set(True)

                    # Show the frame inside the main screen container
                    root.show_screen(EpisodeIDPromptFrame, f"{show} | Folder: {folder_name}", prompt_list, _on_submit_frame, file_names=[file.name for (file,_,_,_) in missing_episodes])
                    root.wait_variable(done_var)
                    # result_container now has mapping passed to _on_submit_frame
                    on_submit(result_container)
                except Exception:
                    # Fallback to Toplevel prompt
                    prompt = EpisodeIDPrompt(root, f"{show} | Folder: {folder_name}", prompt_list, on_submit, file_names=[file.name for (file,_,_,_) in missing_episodes])
                    try:
                        if root is not None:
                            root.wait_window(prompt)
                    except Exception:
                        pass
            else:
                # CLI/standalone mode: keep using the Toplevel-based prompt
                prompt = EpisodeIDPrompt(root, f"{show} | Folder: {folder_name}", prompt_list, on_submit, file_names=[file.name for (file,_,_,_) in missing_episodes])
                try:
                    if root is not None:
                        root.wait_window(prompt)
                except Exception:
                    pass

        # Build planned moves for this show's files
        for file, season, episode, extras in files:
            ep_id = None
            if file.stem in manual_title_cache:
                cached = manual_title_cache[file.stem]
                cached_ids = _episode_id_list(cached)
                if len(cached_ids) > 1:
                    ep_id = cached_ids
                else:
                    ep_id = cached
            elif season is not None and episode is not None:
                ep_id = lookup_episode_id(imdb_id, season, episode, file_stem=file.stem)
            else:
                ep_id = lookup_episode_id(imdb_id, season, episode, file_stem=file.stem)
            _, dest_path = build_episode_path(file, show, season, episode, extras, imdb_id, ep_id, original_file_stem=file.stem)

            try:
                if file.resolve() == dest_path.resolve():
                    # no-op, skip
                    #debug_print(f"[DEBUG] Skipping plan entry (no change): {file} -> {dest_path}")
                    continue
            except Exception:
                if str(file) == str(dest_path):
                    debug_print(f"[DEBUG] Skipping plan entry (no change by string): {file} -> {dest_path}")
                    continue
            planned.append({
                "type": "Series",
                "src": str(file),
                "dest": str(dest_path)
            })
    # Debug: log planned entries types and contents to help trace bad entries
    try:
        for idx, entry in enumerate(planned):
            pass
            # debug_print(...) left commented to avoid local imports overshadowing global debug_print
    except Exception:
        pass
    return planned








# ---------- Main Functionalities ----------