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
    # --- Tkinter dialog for IMDb ID conflict resolution ---
    def prompt_for_imdb_id_conflict(folder_name, conflicting_id, reason):
        """Show a small dialog asking the user to resolve an IMDb ID conflict.

        Returns a manually entered IMDb ID string or None to indicate skip.
        """
        import tkinter as tk
        result = {'imdb_id': None, 'skip': False}
        def on_use():
            val = entry.get().strip()
            if val:
                result['imdb_id'] = val
                root.quit()
        def on_skip():
            result['skip'] = True
            root.quit()
        root = tk.Tk()
        root.title("IMDb ID Conflict")
        root.geometry("400x180")
        tk.Label(root, text=f"Folder: {folder_name}", font=("Arial", 10, "bold")).pack(pady=4)
        tk.Label(root, text=f"Conflicting IMDb ID: {conflicting_id}", fg="red").pack()
        tk.Label(root, text=reason, wraplength=380, fg="darkred").pack(pady=2)
        entry = tk.Entry(root, width=30)
        entry.pack(pady=8)
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=4)
        use_btn = tk.Button(btn_frame, text="Use IMDb ID", command=on_use)
        use_btn.pack(side=tk.LEFT, padx=8)
        skip_btn = tk.Button(btn_frame, text="Skip Folder", command=on_skip)
        skip_btn.pack(side=tk.LEFT, padx=8)
        entry.focus_set()
        root.mainloop()
        root.destroy()
        if result['skip']:
            return None
        return result['imdb_id']
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
        return show_id_map[(show, cache_key)]

    # Load imdb_cache
    import json
    imdb_cache_path = Path(__file__).parent.parent / 'cache' / 'imdb_cache.json'
    try:
        with open(imdb_cache_path, 'r', encoding='utf-8') as f:
            imdb_cache = json.load(f)
    except Exception:
        imdb_cache = {}

    # Normalize folder name for comparisons (replace en-dash etc)
    folder_norm = folder_name.replace('\u2013', '-').replace('\u2014', '-').strip() if folder_name else folder_name

    # First try the imdb_cache lookup using the folder-based key
    cached_imdb_id = imdb_cache.get(cache_key) or imdb_cache.get(folder_norm) or imdb_cache.get(show)
    cached_meta = get_entry(cached_imdb_id) if cached_imdb_id else None


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
            show_id_map[(show, cache_key)] = imdb_id
            return imdb_id

        # If folder has a year(s) and cached meta has year(s), compare
        if cached_type == 'series' and folder_start:
            try:
                fs = int(folder_start) if folder_start else None
                fe = int(folder_end) if folder_end else fs
                ms = int(meta_start) if meta_start else None
                me = int(meta_end) if meta_end else ms
            except Exception:
                fs = folder_start; fe = folder_end; ms = meta_start; me = meta_end

            years_match = False
            if fs is None or ms is None:
                years_match = False
            else:
                try:
                    if isinstance(fs, int) and isinstance(ms, int):
                        if fe >= ms and me >= fs:
                            years_match = True
                    else:
                        if str(fs) == str(ms):
                            years_match = True
                except Exception:
                    years_match = False

            # If the cached ID is already used for a different folder with different years, never use it
            if not years_match:
                debug_print(f"⚠️ Not using cached IMDb ID {cached_imdb_id} for {cache_key}: years do not match.")
                cached_imdb_id = None  # <--- ADD THIS LINE
                cached_meta = None     # <--- ADD THIS LINE
                # Force prompt for new ID below
            else:
                imdb_id = cached_imdb_id
                show_id_map[(show, cache_key)] = imdb_id
                return imdb_id

    # If cached_imdb_id is not present or not acceptable, fall back to GUI search
    while True:
        imdb_id = get_series_imdb_id_gui(cache_key, search_title=show)
        if imdb_id is None:
            debug_print(f"⏭️ Skipped by user: {cache_key}")
            return None

        meta = get_entry(imdb_id)
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
            if manual_id is None:
                debug_print(f"⏭️ Skipped by user: {cache_key}")
                return None
            imdb_id = manual_id
            meta = get_entry(imdb_id)
            # Re-check for conflict
            if imdb_id_used_for_other_series(imdb_id, cache_key, folder_start, folder_end):
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
    from core.series_utils import get_episode_title_from_cache
    canonical_ep_title = get_episode_title_from_cache(ep_id) if ep_id else None
    is_movie_cut_special = False
    if ep_info:
        # If OMDb type is 'movie' but we're in a series context, treat as special
        if ep_info.get('type') == 'movie' and imdb_id:
            override_season = 0
            override_episode = 0
            is_movie_cut_special = True
        if ep_info.get('season') is not None:
            try:
                override_season = int(ep_info['season'])
            except Exception:
                override_season = ep_info['season']
        if ep_info.get('episode') is not None:
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
            # remove punctuation but keep spaces and hyphens
            title = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
            # replace hyphens with spaces so "Ice-Ca" and "Ice Ca" compare equal
            title = title.replace("-", " ")
            title = re.sub(r"\s+", " ", title).strip().lower()
            return title
        

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
            # Try substring match with normalized comparison
            extras_words = e_clean.split()
            match = None
            for i in range(len(extras_words)):
                for j in range(i+1, len(extras_words)+1):
                    candidate = " ".join(extras_words[i:j])
                    if normalize_title(candidate) == norm_canonical:
                        match = candidate
                        break
                if match:
                    break
            if match:
                pattern = re.compile(re.escape(match), flags=re.IGNORECASE)
                replaced = pattern.sub(title_str, e_clean, count=1).strip()
                if normalize_title(replaced) == norm_canonical:
                    new_extras_out.append(title_str)
                else:
                    new_extras_out.append(replaced)
            else:
                norm_e = normalize_title(e_clean)
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
            e_num = int(override_episode)
            if s_num == 0:
                season_folder = "Season 00"
            else:
                season_folder = f"Season {s_num:02}"
            episode_name = f"{series_title} - S{s_num:02}E{e_num:02}"
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
        years_mismatch = False
        if folder_start and meta_start:
            try:
                fs = int(folder_start)
                fe = int(folder_end) if folder_end else fs
                ms = int(meta_start)
                me = int(meta_end) if meta_end else ms
                # mismatch if no overlap
                if fe < ms or me < fs:
                    years_mismatch = True
            except Exception:
                if str(folder_start) != str(meta_start):
                    years_mismatch = True

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
                ep_imdb_id = get_episode_imdb_id_from_filename(file.stem)
                if ep_imdb_id:
                    ep_imdb_id = clean_brackets(ep_imdb_id)
                if ep_imdb_id and is_imdb_id_skipped(ep_imdb_id, file.name):
                    debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_imdb_id})")
                    continue
                imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
                if imdb_id is None:
                    debug_print(f"⏭️ Skipped by user: {file.name}")
                    continue
                ep_id = ep_imdb_id if ep_imdb_id else get_episode_imdb_id(show, imdb_id, season, episode, file_stem=file.stem)
                if ep_id and is_imdb_id_skipped(ep_id, file.name):
                    debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_id})")
                    continue
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
            return

        # Regular processing for files not in skip list
        for file in files:
            debug_print(f"  Processing file: {file.name}")
            show, season, episode, extras = extract_episode_info(file.stem)
            if not show:
                continue
            ep_imdb_id = get_episode_imdb_id_from_filename(file.stem)
            if ep_imdb_id and is_imdb_id_skipped(ep_imdb_id, file.name):
                debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_imdb_id})")
                continue
            imdb_id = get_or_prompt_show_imdb_id(show, folder_name, show_id_map)
            if imdb_id is None:
                debug_print(f"⏭️ Skipped by user: {file.name}")
                continue
            ep_id = get_episode_imdb_id(show, imdb_id, season, episode)
            if ep_id and is_imdb_id_skipped(ep_id, file.name):
                debug_print(f"🎬 Skipping episode (ID in skip list): {file.name} (ID: {ep_id})")
                continue
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
            ep_imdb_id = get_episode_imdb_id_from_filename(file.stem)
            if ep_imdb_id:
                ep_imdb_id = clean_brackets(ep_imdb_id)
            ep_id = ep_imdb_id if ep_imdb_id else get_episode_imdb_id(show, imdb_id, season, episode, file_stem=file.stem)

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

        # Batch prompt for missing episode IDs using the GUI prompt component
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

        # Build planned moves for this show's files
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