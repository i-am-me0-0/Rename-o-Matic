# actions/manual_series_tvdb_scraper.py
#
# Same blank-slate behaviour as the plain blank-slate script (parses filenames
# with core.info_extractors.extract_episode_info, builds "Show (Year) [ID]/
# Season SS/Show - SxxEyy [extras].ext" paths, never touches imdb_cache.json,
# media_metadata_cache, or the OMDb scraper) -- PLUS optional TVDB enrichment
# (year, TVDB show id, episode titles, episode ids) fetched live and kept only
# in memory for this run.
#
# This is wired up from the app menu via:
#   from actions.manual_series_tvdb_scraper import main
#   main()
# which runs as a Tkinter button callback -- there is no console attached, so
# unlike a bare CLI script this version NEVER calls input()/print() to ask the
# user anything. All prompts (season order, "what's this show's TVDB URL?")
# are Tk Toplevel dialogs that grab focus and block via root.wait_window(),
# the same pattern used elsewhere in this project (see gui.episode_id_prompt).
#
# NOTE: the TVDB fetches below are plain blocking `requests.get()` calls made
# on the main/GUI thread inside a menu callback, so the window will look frozen
# while a show's episode list is downloading. That's acceptable for the small
# number of shows typically involved, but if you want this backgrounded, it
# would need to move onto a worker thread the same way the OMDb scraper does
# (see actions/omdb_gui_scraper.safe_request).

import json
import re
import tkinter as tk
from pathlib import Path
from typing import Optional, Dict, Any

from config import SERIES_DIR, PLANNED_RENAMES_FILE
from core.file_utils import is_video_file
from core.info_extractors import extract_episode_info

YEAR_PLACEHOLDER = "YEAR"
IMDB_PLACEHOLDER = "ttXXXXXXX"

IMDB_ID_RE = re.compile(r'(tt\d{7,8})')
# Matches "(2007)" or "(1982-1986)" / "(1982-1986)" (en/em dash) embedded in a title
EMBEDDED_YEAR_RE = re.compile(r'\s*\((\d{4})(?:\s*[-\u2013\u2014]\s*(\d{4}))?\)\s*')


# ==============================================================================
# TK DIALOGS (replace input()/print() prompts so this works from a GUI menu)
# ==============================================================================

def _get_root() -> tk.Tk:
    """Reuse the app's existing Tk root if one is already running; otherwise
    create a hidden one. Using tk._default_root avoids spinning up a second,
    competing Tk() instance when this is called from inside the running app.
    """
    root = tk._default_root
    if root is None:
        root = tk.Tk()
        root.withdraw()
    return root


def prompt_season_order_tk(show_title: str = "") -> int:
    """Modal season-order picker. Returns 0=Aired, 1=DVD, 2=Absolute.

    Replaces the old `input("Pick a season order (1-3, default=1): ")` call,
    which would silently hang with no stdin attached when launched from the menu.
    """
    root = _get_root()
    win = tk.Toplevel(root)
    win.title("Select Season Order")
    win.transient(root)
    win.grab_set()
    win.resizable(False, False)

    result = {"choice": 0}

    label_text = f"Pick a season order for:\n{show_title}" if show_title else "Pick a season order"
    tk.Label(win, text=label_text, padx=20, pady=10, justify="left").pack()

    options = ["Aired Order", "DVD Order", "Absolute Order", "Streaming Order"]
    var = tk.IntVar(value=0)
    for i, label in enumerate(options):
        tk.Radiobutton(win, text=label, variable=var, value=i).pack(anchor="w", padx=20)

    def on_ok():
        result["choice"] = var.get()
        win.destroy()

    tk.Button(win, text="OK", command=on_ok, padx=10).pack(pady=10)
    win.protocol("WM_DELETE_WINDOW", on_ok)  # closing the window = accept current selection

    win.update_idletasks()
    try:
        win.geometry(f"+{root.winfo_x() + 60}+{root.winfo_y() + 60}")
    except Exception:
        pass

    root.wait_window(win)
    return result["choice"]


def prompt_for_tvdb_url_tk(show_title: str) -> Optional[str]:
    """Ask the user for a TheTVDB series URL for a show that isn't cached yet.
    Returns None if skipped (that show is simply left un-enriched with
    YEAR/ttXXXXXXX placeholders, same as the plain blank-slate script).
    """
    root = _get_root()
    win = tk.Toplevel(root)
    win.title(f"TVDB URL for: {show_title}")
    win.transient(root)
    win.grab_set()
    win.resizable(False, False)

    result = {"url": None}

    tk.Label(
        win,
        text=f"Enter TheTVDB series URL for:\n{show_title}\n(leave blank and click Skip to use placeholders instead)",
        padx=20, pady=10, justify="left"
    ).pack()

    entry = tk.Entry(win, width=60)
    entry.pack(padx=20, pady=5)
    entry.focus_set()

    def on_ok():
        val = entry.get().strip()
        result["url"] = val or None
        win.destroy()

    def on_skip():
        result["url"] = None
        win.destroy()

    btn_frame = tk.Frame(win)
    btn_frame.pack(pady=10)
    tk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Skip", command=on_skip, width=10).pack(side="left", padx=5)

    win.protocol("WM_DELETE_WINDOW", on_skip)
    win.bind("<Return>", lambda e: on_ok())

    win.update_idletasks()
    try:
        win.geometry(f"+{root.winfo_x() + 60}+{root.winfo_y() + 60}")
    except Exception:
        pass

    root.wait_window(win)
    return result["url"]


def _warn_tk(message: str):
    try:
        from tkinter import messagebox
        messagebox.showwarning("Series Renamer", message, parent=_get_root())
    except Exception:
        # Last-resort fallback if messagebox itself can't be shown for some reason.
        pass


# ==============================================================================
# IN-MEMORY TVDB SCRAPER (no file writes; caches results per run only)
# ==============================================================================

_TVDB_CACHE: Dict[str, Dict[str, Any]] = {}
_SHOW_URL_SESSION: Dict[str, Optional[str]] = {}  # show name -> chosen URL or None (skipped)


def fetch_tvdb_metadata(series_url: str, show_title: str = "") -> Dict[str, Any]:
    """Scrape TVDB for show metadata + episode list. In-memory only, no disk writes."""
    if series_url in _TVDB_CACHE:
        return _TVDB_CACHE[series_url]

    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        _warn_tk("Install 'requests' and 'beautifulsoup4' to use the TVDB scraper.\n"
                  "Continuing with placeholders for this show.")
        return {}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(series_url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        _warn_tk(f"Failed to fetch TVDB page for '{show_title or series_url}':\n{e}\n"
                  f"Continuing with placeholders for this show.")
        return {}

    soup = BeautifulSoup(response.text, 'html.parser')

    title_tag = soup.find('h1') or soup.find('title')
    full_title = title_tag.text.strip() if title_tag else "Unknown Show"
    show_title_scraped = re.sub(r'\s*-\s*TheTVDB\.com\s*$', '', full_title, flags=re.IGNORECASE).strip()

    year_match = re.search(r'\((\d{4})\)', show_title_scraped)
    year = year_match.group(1) if year_match else "YEAR"

    tvdb_show_id = "TVDB_UNKNOWN"
    id_match = re.search(r'"series_id":\s*(\d+)', response.text) or re.search(r'series/(\d+)', response.text)
    if id_match:
        tvdb_show_id = id_match.group(1)

    base_url = series_url.rstrip('/')

    season_types = [
        ("Aired Order", f"{base_url}/seasons/official/"),
        ("DVD Order", f"{base_url}/seasons/dvd/"),
        ("Absolute Order", f"{base_url}/seasons/absolute/"),
        ("Streaming Order", f"{base_url}/seasons/alternate/"),
    ]

    choice_idx = prompt_season_order_tk(show_title_scraped or show_title)
    selected_name, selected_base = season_types[choice_idx]

    all_seasons_url = f"{base_url}/allseasons/{selected_base.split('/')[-2]}"

    episodes_data = []
    try:
        resp_all = requests.get(all_seasons_url, headers=headers, timeout=15)
    except Exception:
        resp_all = None

    def _parse_episode_rows(soup_obj, default_season=None):
        rows = []
        for a in soup_obj.find_all('a', href=True):
            if '/episodes/' in a['href']:
                ep_url = a['href']
                ep_id_match = re.search(r'/episodes/(\d+)', ep_url)
                ep_id = ep_id_match.group(1) if ep_id_match else None

                tr = a.find_parent('tr')
                if tr:
                    cols = tr.find_all('td')
                    if len(cols) > 0:
                        ep_num_text = cols[0].text.strip()
                        ep_title = a.text.strip()

                        se_match = re.search(r'S(\d+)E(\d+)', ep_num_text, re.IGNORECASE)
                        if se_match:
                            season = int(se_match.group(1))
                            episode = int(se_match.group(2))
                        else:
                            season = default_season if default_season is not None else 0
                            episode = 0

                        rows.append({
                            "season": season,
                            "episode": episode,
                            "title": ep_title,
                            "tvdb_id": ep_id,
                            "url": f"https://www.thetvdb.com{ep_url}"
                        })
        return rows

    if resp_all is not None and resp_all.status_code == 200:
        soup_all = BeautifulSoup(resp_all.text, 'html.parser')
        episodes_data = _parse_episode_rows(soup_all)
    else:
        # Fall back to iterating seasons 1-20 individually
        for season_num in range(1, 21):
            season_url = f"{selected_base}{season_num}"
            try:
                resp = requests.get(season_url, headers=headers, timeout=15)
            except Exception:
                continue
            if resp.status_code != 200:
                continue
            soup_season = BeautifulSoup(resp.text, 'html.parser')
            episodes_data.extend(_parse_episode_rows(soup_season, default_season=season_num))

    episodes_data.sort(key=lambda x: (x["season"], x["episode"]))

    result = {
        "show_title": show_title_scraped,
        "year": year,
        "tvdb_show_id": tvdb_show_id,
        "season_order": selected_name,
        "episodes": episodes_data
    }

    _TVDB_CACHE[series_url] = result
    return result


def get_episode_from_cache(series_url: str, season: int, episode: Any, show_title: str = "") -> Optional[Dict[str, Any]]:
    metadata = fetch_tvdb_metadata(series_url, show_title=show_title)
    if not metadata:
        return None

    if isinstance(episode, (list, tuple)):
        target_episodes = [int(e) for e in episode if str(e).isdigit()]
    elif episode is not None:
        target_episodes = [int(episode)]
    else:
        return None

    if not target_episodes:
        return None

    first_ep = target_episodes[0]
    for ep in metadata["episodes"]:
        if ep["season"] == season and ep["episode"] == first_ep:
            return ep
    return None


def get_tvdb_url_for_show(show: str) -> Optional[str]:
    """Interactive replacement for the old static SHOW_TVDB_MAP dict.
    Prompts once per show per run and remembers the choice (including "skip").
    """
    if show in _SHOW_URL_SESSION:
        return _SHOW_URL_SESSION[show]
    url = prompt_for_tvdb_url_tk(show)
    _SHOW_URL_SESSION[show] = url
    return url


# ==============================================================================
# BLANK-SLATE PATH BUILDING (same conventions as the plain blank-slate script)
# ==============================================================================

def build_episode_suffix(episode):
    if isinstance(episode, (list, tuple)):
        nums = [int(e) for e in episode if str(e).isdigit()]
        if not nums:
            return "E00"
        return "E" + "E".join(f"{n:02}" for n in nums)
    if episode is not None:
        return f"E{int(episode):02}"
    return "E00"


def extract_embedded_year(show_text: str):
    m = EMBEDDED_YEAR_RE.search(show_text)
    if not m:
        return show_text.strip(), None
    start, end = m.group(1), m.group(2)
    year_str = f"{start}-{end}" if end and end != start else start
    cleaned = (show_text[:m.start()] + " " + show_text[m.end():]).strip()
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(" -")
    return cleaned, year_str


def extract_embedded_imdb_id(text: str):
    if not text:
        return None
    m = IMDB_ID_RE.search(text)
    return m.group(1) if m else None


def build_to_path(file: Path):
    ext = file.suffix
    show_raw, season, episode, extras = extract_episode_info(file.stem)

    show_raw = (show_raw or "UNKNOWN_SHOW").strip()
    season = season if season is not None else 1

    show, embedded_year = extract_embedded_year(show_raw)

    year_str = embedded_year or YEAR_PLACEHOLDER
    show_id = (
        extract_embedded_imdb_id(show_raw)
        or extract_embedded_imdb_id(file.parent.name)
        or IMDB_PLACEHOLDER
    )
    ep_title = ""

    # --- TVDB enrichment (optional, per-show, session-cached) ---
    tvdb_url = get_tvdb_url_for_show(show)
    if tvdb_url:
        metadata = fetch_tvdb_metadata(tvdb_url, show_title=show)
        if metadata:
            if not embedded_year and metadata.get("year") and metadata["year"] != "YEAR":
                year_str = metadata["year"]
            if show_id == IMDB_PLACEHOLDER and metadata.get("tvdb_show_id") not in (None, "TVDB_UNKNOWN"):
                show_id = f"tvdb{metadata['tvdb_show_id']}"
            ep_data = get_episode_from_cache(tvdb_url, season, episode, show_title=show)
            if ep_data and ep_data.get("title"):
                ep_title = ep_data["title"]
    # ---------------------------------------------------------------

    season_str = f"S{season:02}"
    ep_str = build_episode_suffix(episode)

    show_folder = f"{show} ({year_str}) [{show_id}]"
    season_folder = f"Season {season:02}"

    episode_filename = f"{show} - {season_str}{ep_str}"
    if ep_title:
        episode_filename += f" - {ep_title}"
    if extras:
        episode_filename += f" [{extras}]"
    episode_filename += ext

    return Path(SERIES_DIR) / show_folder / season_folder / episode_filename


def main():
    planned = []
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


if __name__ == "__main__":
    main()