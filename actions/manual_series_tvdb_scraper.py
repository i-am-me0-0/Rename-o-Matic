# actions/manual_series_tvdb_scraper.py
#
# Same blank-slate behaviour as the plain blank-slate script (parses filenames
# with core.info_extractors.extract_episode_info, builds "Show (Year) [ID]/
# Season SS/Show - SxxEyy [extras].ext" paths, plus optional TVDB enrichment
# that persists (year, TVDB show id, episode titles, episode ids) in
# imdb_cache.json and media_metadata.json for use by the normal preview.
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
import os
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlsplit, urlunsplit

from config import SERIES_DIR, PLANNED_RENAMES_FILE, IMDB_CACHE_FILE
from core.file_utils import is_video_file
from core.info_extractors import extract_episode_info
from core.media_metadata_cache import set_entry, add_episode_to_series

YEAR_PLACEHOLDER = "YEAR"
IMDB_PLACEHOLDER = "ttXXXXXXX"
TVDB_DEBUG = False

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
    root = getattr(tk, "_default_root", None)
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

    result: Dict[str, Optional[str]] = {"url": None}

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
    win.bind("<Return>", lambda event: on_ok() if event is not None else on_ok())

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
# TVDB SCRAPER WITH DISK CACHE SUPPORT
# ==============================================================================

_TVDB_CACHE: Dict[str, Dict[str, Any]] = {}
_SHOW_URL_SESSION: Dict[str, Optional[str]] = {}  # show name -> chosen URL or None (skipped)


def _tvdb_debug(message: str) -> None:
    if TVDB_DEBUG:
        print(f"[TVDB] {message}", flush=True)


def _optional_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def is_tvdb_id(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"tvdb\d+", value, re.I) is not None


def _load_imdb_cache() -> Dict[str, str]:
    try:
        with open(IMDB_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_imdb_cache(cache: Dict[str, str]) -> None:
    IMDB_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = IMDB_CACHE_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    try:
        os.replace(tmp_path, IMDB_CACHE_FILE)
    except Exception:
        tmp_path.replace(IMDB_CACHE_FILE)


def persist_tvdb_metadata(metadata: Dict[str, Any]) -> str:
    """Persist a scraped series and its episode mappings in the normal app caches."""
    tvdb_show_id = str(metadata.get("tvdb_show_id") or "")
    if not tvdb_show_id.isdigit():
        _tvdb_debug(f"Cannot persist cache: no numeric TVDB show ID (got {tvdb_show_id!r})")
        return ""

    series_id = f"tvdb{tvdb_show_id}"
    show_title = str(metadata.get("show_title") or "").strip()
    year = metadata.get("year")
    from core.media_metadata_cache import get_entry
    existing_series = get_entry(series_id) or {}

    series_entry = {
        "title": show_title,
        "year": None if year == "YEAR" else year,
        "end_year": None if not metadata.get("end_year") or metadata.get("end_year") == "YEAR" else metadata.get("end_year"),
        "type": "series",
        "tvdb_id": tvdb_show_id,
        "season_order": metadata.get("season_order"),
        "episodes": existing_series.get("episodes", {}) if isinstance(existing_series.get("episodes", {}), dict) else {},
    }
    set_entry(series_id, series_entry)

    for ep in metadata.get("episodes", []):
        season = _optional_int(ep.get("season"))
        episode = _optional_int(ep.get("episode"))
        ep_id = ep.get("tvdb_id")
        if season is None or episode is None:
            continue

        if ep_id:
            episode_id = f"tvdb{ep_id}"
        else:
            episode_id = f"tvdb{tvdb_show_id}-S{int(season):02}E{int(episode):02}"

        episode_entry = {
            "title": ep.get("title") or "",
            "year": ep.get("aired_year") or (year if year != "YEAR" else None),
            "type": "episode",
            "tvdb_id": str(ep_id or ""),
            "series_id": series_id,
            "season": int(season),
            "episode": int(episode),
            "summary": ep.get("summary") or "",
            "poster_url": ep.get("poster_url") or "",
            "url": ep.get("url") or "",
        }
        set_entry(episode_id, episode_entry)
        add_episode_to_series(
            series_id,
            str(season),
            str(episode),
            episode_id,
            episode_entry,
        )

    try:
        from core.media_metadata_cache import flush_metadata, load_metadata
        flushed = flush_metadata(load_metadata())
        if not flushed:
            _warn_tk("TVDB metadata could not be written cleanly to media_metadata.json, please retry.")
    except Exception as e:
        _tvdb_debug(f"Could not synchronously flush media metadata cache: {e}")

    _tvdb_debug(f"Prepared TVDB show cache key={show_title!r}, series_id={series_id}")
    try:
        from core.media_metadata_cache import get_entry
        verify_series = get_entry(series_id)
        episode_count = len(verify_series.get("episodes", {})) if verify_series else 0
        _tvdb_debug(
            f"media_metadata verification: series={series_id}, "
            f"has_entry={bool(verify_series)}, season_maps={episode_count}"
        )
    except Exception as e:
        _tvdb_debug(f"media_metadata verification failed: {e}")
    _tvdb_debug(
        f"Saved TVDB cache: show={show_title!r}, series_id={series_id}, "
        f"episodes={len(metadata.get('episodes', []))}, cache={IMDB_CACHE_FILE}"
    )
    return series_id


def fetch_tvdb_metadata(series_url: str, show_title: str = "") -> Dict[str, Any]:
    """Scrape TVDB for show metadata + episode list and persist it to app caches."""
    url_parts = urlsplit(str(series_url).strip())
    if url_parts.scheme and url_parts.netloc:
        series_url = urlunsplit((url_parts.scheme, url_parts.netloc, url_parts.path.rstrip("/"), "", ""))
    else:
        series_url = str(series_url).strip().split("#", 1)[0].rstrip("/")
    _tvdb_debug(f"Normalized TVDB URL: {series_url}")

    if series_url in _TVDB_CACHE:
        _tvdb_debug(f"Using in-session cache for {series_url}")
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
        _tvdb_debug(f"Series page fetched: status={response.status_code}, url={response.url}")
    except Exception as e:
        _tvdb_debug(f"Series page failed: url={series_url}, error={e}")
        _warn_tk(f"Failed to fetch TVDB page for '{show_title or series_url}':\n{e}\n"
                  f"Continuing with placeholders for this show.")
        return {}

    soup = BeautifulSoup(response.text, 'html.parser')

    title_tag = soup.find('h1') or soup.find('title')
    full_title = title_tag.text.strip() if title_tag else "Unknown Show"
    show_title_scraped = re.sub(r'\s*-\s*TheTVDB\.com\s*$', '', full_title, flags=re.IGNORECASE).strip()

    year_match = re.search(r'\((\d{4})\)', show_title_scraped)
    year = year_match.group(1) if year_match else "YEAR"
    end_year: Optional[str] = None
    first_year, end_year = extract_tvdb_year_range(soup)
    if year == "YEAR" and first_year:
        year = first_year

    if year == "YEAR":
        year_patterns = [
            r'<meta[^>]+(?:property|name)="(?:og:title|twitter:title|release_date|date)"[^>]+content="[^"]*?\b(19\d{2}|20\d{2})\b',
            r'(?:First Aired|Year|Release Year)[^\d]{0,40}(19\d{2}|20\d{2})',
            r'"(?:year|firstAired|first_aired)"\s*:\s*"?((?:19|20)\d{2})',
        ]
        for pattern in year_patterns:
            year_match = re.search(pattern, response.text, re.I)
            if year_match:
                year = year_match.group(1)
                break

    tvdb_show_id = "TVDB_UNKNOWN"
    id_patterns = [
        r'"series_id"\s*:\s*(\d+)',
        r'"seriesId"\s*:\s*(\d+)',
        r'"id"\s*:\s*(\d+)',
        r'(?:artworks\.thetvdb\.com/)?banners/episodes/(\d+)/',
        r'(?:artworks\.thetvdb\.com/)?banners/posters/(\d+)-',
    ]
    id_match = re.search(r'/series/(\d+)', response.url) or re.search(r'/series/(\d+)', series_url)
    if id_match is None:
        for pattern in id_patterns:
            id_match = re.search(pattern, response.text, re.I)
            if id_match is not None:
                break
    if id_match:
        tvdb_show_id = id_match.group(1)
    _tvdb_debug(
        f"Parsed show: title={show_title_scraped!r}, year={year}, "
        f"tvdb_show_id={tvdb_show_id}"
    )

    base_url = series_url.rstrip('/')

    season_types = [
        ("Aired Order", f"{base_url}/seasons/official/"),
        ("DVD Order", f"{base_url}/seasons/dvd/"),
        ("Absolute Order", f"{base_url}/seasons/absolute/"),
        ("Streaming Order", f"{base_url}/seasons/alternate/"),
    ]

    choice_idx = prompt_season_order_tk(show_title_scraped or show_title)
    selected_name, selected_base = season_types[choice_idx]
    _tvdb_debug(f"Season order selected: {selected_name}")

    all_seasons_url = f"{base_url}/allseasons/{selected_base.split('/')[-2]}"
    _tvdb_debug(f"Trying all-seasons URL: {all_seasons_url}")

    episodes_data = []
    try:
        resp_all = requests.get(all_seasons_url, headers=headers, timeout=15)
        _tvdb_debug(f"All-seasons response: status={resp_all.status_code}, url={resp_all.url}")
    except Exception as e:
        _tvdb_debug(f"All-seasons request failed: url={all_seasons_url}, error={e}")
        resp_all = None

    def _parse_episode_rows(soup_obj, default_season=None):
        rows = []

        for item in soup_obj.select("li.list-group-item"):
            label_tag = item.select_one(".episode-label")
            link_tag = item.select_one("h4 a[href*='/episodes/']")
            if label_tag is None or link_tag is None:
                continue

            se_match = re.search(
                r'S(\d+)E(\d+)',
                label_tag.get_text(" ", strip=True),
                re.IGNORECASE,
            )
            if se_match:
                season = int(se_match.group(1))
                episode = int(se_match.group(2))
            else:
                season = default_season if default_season is not None else 0
                episode = 0

            ep_url = str(link_tag.get("href") or "")
            ep_id_match = re.search(r'/episodes/(\d+)', ep_url)
            ep_id = ep_id_match.group(1) if ep_id_match else None
            summary_tag = item.select_one(".list-group-item-text p")
            poster_tag = item.select_one("img[data-src]")
            poster_url = str(poster_tag.get("data-src") or "") if poster_tag else ""
            date_tag = item.select_one(".list-inline li")
            aired_year = None
            if date_tag:
                date_match = re.search(r"\b((?:19|20)\d{2})\b", date_tag.get_text(" ", strip=True))
                if date_match:
                    aired_year = date_match.group(1)

            rows.append({
                "season": season,
                "episode": episode,
                "title": link_tag.get_text(" ", strip=True),
                "tvdb_id": ep_id,
                "url": ep_url if ep_url.startswith("http") else f"https://www.thetvdb.com{ep_url}",
                "summary": summary_tag.get_text(" ", strip=True) if summary_tag else "",
                "poster_url": poster_url,
                "aired_year": aired_year,
            })

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

                        if episode == 0:
                            for col in cols:
                                nums = re.findall(r'\d+', col.text)
                                if nums:
                                    episode = int(nums[-1])
                                    break

                        rows.append({
                            "season": season,
                            "episode": episode,
                            "title": ep_title,
                            "tvdb_id": ep_id,
                            "url": ep_url if ep_url.startswith("http") else f"https://www.thetvdb.com{ep_url}",
                        })
        return rows

    def _parse_embedded_episode_json(html_text: str) -> list:
        parsed_rows = []
        for script in re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.I | re.S):
            script = script.strip()
            if not script:
                continue
            for match in re.findall(r'(\{.*?\}|\[.*?\])', script, re.S):
                try:
                    payload = json.loads(match)
                except Exception:
                    continue

                def walk(value):
                    if isinstance(value, dict):
                        keys = {str(k).lower(): v for k, v in value.items()}
                        ep_id = keys.get("id") or keys.get("episodeid") or keys.get("episode_id")
                        season = keys.get("airedseason") or keys.get("seasonnumber") or keys.get("season")
                        episode = keys.get("airedepisodenumber") or keys.get("episodenumber") or keys.get("episode")
                        title = keys.get("name") or keys.get("title")
                        summary = keys.get("overview") or keys.get("summary")
                        try:
                            season_int = _optional_int(season)
                            episode_int = _optional_int(episode)
                            ep_id_int = _optional_int(ep_id)
                            if season_int is None or episode_int is None:
                                raise ValueError("Missing episode number or season")
                            if season_int >= 0 and episode_int > 0 and title:
                                parsed_rows.append({
                                    "season": season_int,
                                    "episode": episode_int,
                                    "title": str(title).strip(),
                                    "tvdb_id": str(ep_id_int) if ep_id_int else None,
                                    "summary": str(summary).strip() if summary else "",
                                    "url": "",
                                })
                        except Exception:
                            pass
                        for child in value.values():
                            walk(child)
                    elif isinstance(value, list):
                        for child in value:
                            walk(child)

                walk(payload)
        return parsed_rows

    if resp_all is not None and resp_all.status_code == 200:
        soup_all = BeautifulSoup(resp_all.text, 'html.parser')
        episodes_data = _parse_episode_rows(soup_all)
        episodes_data.extend(_parse_embedded_episode_json(resp_all.text))
    else:
        # Fall back to iterating seasons 1-20 individually
        _tvdb_debug("All-seasons page unavailable; trying individual season pages")
        for season_num in range(1, 21):
            season_url = f"{selected_base}{season_num}"
            try:
                resp = requests.get(season_url, headers=headers, timeout=15)
            except Exception as e:
                _tvdb_debug(f"Season request failed: season={season_num}, error={e}")
                continue
            if resp.status_code != 200:
                continue
            _tvdb_debug(f"Season page fetched: season={season_num}, status={resp.status_code}")
            soup_season = BeautifulSoup(resp.text, 'html.parser')
            episodes_data.extend(_parse_episode_rows(soup_season, default_season=season_num))
            episodes_data.extend(_parse_embedded_episode_json(resp.text))

    deduplicated = {}
    for ep in episodes_data:
        if ep.get("season") is None or ep.get("episode") is None:
            continue
        key = (int(ep["season"]), int(ep["episode"]))
        existing = deduplicated.get(key)
        if existing is None or (not existing.get("tvdb_id") and ep.get("tvdb_id")):
            deduplicated[key] = ep

    episodes_data = [deduplicated[key] for key in sorted(deduplicated)]
    if end_year is None:
        aired_years = [
            int(ep["aired_year"])
            for ep in episodes_data
            if str(ep.get("aired_year") or "").isdigit()
        ]
        end_year = str(max(aired_years)) if aired_years else None
    if end_year == year:
        end_year = None
    _tvdb_debug(
        f"Parsed episode count={len(episodes_data)} "
        f"(first={episodes_data[0] if episodes_data else None}, "
        f"last={episodes_data[-1] if episodes_data else None})"
    )

    result = {
        "show_title": show_title_scraped,
        "year": year,
        "end_year": end_year,
        "tvdb_show_id": tvdb_show_id,
        "season_order": selected_name,
        "episodes": episodes_data
    }

    _TVDB_CACHE[series_url] = result
    persist_tvdb_metadata(result)
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
    _tvdb_debug(
        f"No TVDB episode match: show={show_title!r}, season={season}, "
        f"episode={first_ep}"
    )
    return None


def get_tvdb_url_for_show(show: str, cache_key: Optional[str] = None) -> Optional[str]:
    """Interactive replacement for the old static SHOW_TVDB_MAP dict.
    Prompts once per show per run and remembers the choice (including "skip").
    """
    session_key = cache_key or show
    if session_key in _SHOW_URL_SESSION:
        return _SHOW_URL_SESSION[session_key]
    url = prompt_for_tvdb_url_tk(show)
    _SHOW_URL_SESSION[session_key] = url
    _tvdb_debug(
        f"User TVDB URL choice for show={show!r}, path_key={session_key!r}: "
        f"{url or 'SKIPPED'}"
    )
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


def format_tvdb_episode_name(
    show: str,
    season: int,
    episode: Any,
    ep_title: str = "",
    extras: Any = None,
    ep_id: str = "",
) -> str:
    season_str = f"S{season:02}"
    ep_str = build_episode_suffix(episode)
    name = f"{show} - {season_str}{ep_str}"

    middle_parts = []
    if ep_title:
        middle_parts.append(str(ep_title).strip())
    if extras:
        if isinstance(extras, (list, tuple, set)):
            middle_parts.extend(str(part).strip() for part in extras if str(part).strip())
        else:
            middle_parts.append(str(extras).strip())
    if middle_parts:
        name += f" [{' - '.join(middle_parts)}]"
    if ep_id:
        name += f" [{ep_id}]"
    name = re.sub(r"\s*-\s*-\s*", " - ", name)
    name = re.sub(r"\s{2,}", " ", name)
    return name


def extract_tvdb_year_range(soup: Any) -> tuple[Optional[str], Optional[str]]:
    first_year: Optional[str] = None
    recent_year: Optional[str] = None
    for li in soup.select("li.list-group-item"):
        text = li.get_text(" ", strip=True)
        first_match = re.search(
            r"First\s+Aired\s+.*?\b((?:19|20)\d{2})\b",
            text,
            re.I,
        )
        recent_match = re.search(
            r"Recent\s+.*?\b((?:19|20)\d{2})\b",
            text,
            re.I,
        )
        if first_match:
            first_year = first_match.group(1)
        if recent_match:
            recent_year = recent_match.group(1)

    if first_year and recent_year and recent_year == first_year:
        recent_year = None
    return first_year, recent_year


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


def get_tvdb_cache_key(file: Path, show: str) -> Optional[str]:
    """Return the real series folder key, excluding the configured SERIES_DIR root."""
    try:
        file_parent = file.parent.resolve()
        series_root = Path(SERIES_DIR).resolve()
        if file_parent == series_root:
            return show.strip() or None

        try:
            relative_parent = file_parent.relative_to(series_root)
        except ValueError:
            return show.strip() or None

        parts = relative_parent.parts
        if not parts:
            return show.strip() or None

        last_part = parts[-1] if len(parts) > 0 else ""
        if re.match(r"^(?:s\d+|season\s*\d+)$", last_part, re.I):
            if len(parts) >= 2:
                parent_part = parts[-2]
                return parent_part.strip() or None

        return last_part.strip() or show.strip() or None
    except Exception as e:
        _tvdb_debug(f"Could not derive TVDB cache key for {file}: {e}")
        return show.strip() or None


def build_to_path(file: Path):
    ext = file.suffix
    show_raw, season, episode, extras = extract_episode_info(file.stem)
    _tvdb_debug(
        f"Processing file={file.name}, extracted_show={show_raw!r}, "
        f"season={season}, episode={episode}"
    )

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
    ep_id = ""

    # --- TVDB enrichment (optional, per-folder, session-cached) ---
    cache_key = get_tvdb_cache_key(file, show)
    tvdb_url = get_tvdb_url_for_show(show, cache_key)
    if tvdb_url:
        metadata = fetch_tvdb_metadata(tvdb_url, show_title=show)
        if metadata:
            if not embedded_year and metadata.get("year") and metadata["year"] != "YEAR":
                year_str = metadata["year"]
                end_year = metadata.get("end_year")
                if end_year and str(end_year) != str(year_str):
                    year_str = f"{year_str}-{end_year}"
            if show_id == IMDB_PLACEHOLDER and metadata.get("tvdb_show_id") not in (None, "TVDB_UNKNOWN"):
                show_id = f"tvdb{metadata['tvdb_show_id']}"
                cache = _load_imdb_cache()
                cache_key = get_tvdb_cache_key(file, show)
                folder_key = cache_key
                cache_changed = False
                if folder_key:
                    if cache.get(folder_key) != show_id:
                        cache[folder_key] = show_id
                        cache_changed = True
                        _tvdb_debug(f"Saved TVDB cache mapping: {folder_key!r} -> {show_id}")
                if show != folder_key and is_tvdb_id(cache.get(show)):
                    del cache[show]
                    cache_changed = True
                    _tvdb_debug(f"Removed TVDB show-title cache mapping: {show!r}")
                try:
                    series_root_key = Path(SERIES_DIR).resolve().name
                    if series_root_key and cache.get(series_root_key) == show_id:
                        del cache[series_root_key]
                        cache_changed = True
                        _tvdb_debug(
                            f"Removed invalid configured-series-root cache mapping: "
                            f"{series_root_key!r}"
                        )
                except Exception as e:
                    _tvdb_debug(f"Could not remove invalid series-root cache mapping: {e}")
                if cache_changed:
                    _save_imdb_cache(cache)
            ep_data = get_episode_from_cache(tvdb_url, season, episode, show_title=show)
            if ep_data and ep_data.get("title"):
                ep_title = ep_data["title"]
            if ep_data and ep_data.get("tvdb_id"):
                ep_id = f"tvdb{ep_data['tvdb_id']}"
    # ---------------------------------------------------------------

    show_folder = f"{show} ({year_str}) [{show_id}]"
    season_folder = f"Season {season:02}"

    episode_filename = format_tvdb_episode_name(
        show,
        season,
        episode,
        ep_title=ep_title,
        extras=extras,
        ep_id=ep_id,
    )
    episode_filename += ext

    destination = Path(SERIES_DIR) / show_folder / season_folder / episode_filename
    try:
        from actions.preview import validate_and_sanitize_path
        destination = Path(validate_and_sanitize_path(str(destination)))
    except Exception as e:
        _tvdb_debug(f"Normal filename sanitizer unavailable, using unsanitized path: {e}")
    return destination


def main():
    _tvdb_debug(f"Starting TVDB scraper. Series directory: {SERIES_DIR}")
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
    print(
        f"Planned renames written to {PLANNED_RENAMES_FILE}: "
        f"{len(planned)} episode(s).",
        flush=True,
    )


if __name__ == "__main__":
    main()