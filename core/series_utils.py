# series_utils.py
# Utility functions for series renamer logic
from pathlib import Path
import json
import re
from core.media_metadata_cache import get_entry
from config import debug_print, SKIP_IMDB_IDS

def clean_brackets(text):
    cleaned = text.strip()
    if (cleaned.startswith("[") and cleaned.endswith("]")) or (cleaned.startswith("(") and cleaned.endswith(")")):
        cleaned = cleaned[1:-1].strip()
    return cleaned

def get_folder_imdb_id(folder_name):
    # Try to get from folder name
    m_folder = re.search(r'(tt\d{7,8})', folder_name)
    if m_folder:
        return m_folder.group(1)
    # Try to get from imdb_cache (canonical lookup)
    imdb_cache_path = Path(__file__).parent.parent / 'cache' / 'imdb_cache.json'
    try:
        with open(imdb_cache_path, 'r', encoding='utf-8') as f:
            imdb_cache = json.load(f)
    except Exception:
        imdb_cache = {}
    return imdb_cache.get(folder_name)

def get_episode_imdb_id_from_filename(filename):
    m_file = re.search(r'(tt\d{7,8})', filename)
    if m_file:
        return m_file.group(1)
    return None

def is_imdb_id_skipped(imdb_id, name_or_skip_list):
    """
    Returns True if the given IMDb ID is in the skip list.
    """
    #print("i was run")
    from config import SKIP_IMDB_IDS
    # If second arg is a list, use it as skip list
    if isinstance(name_or_skip_list, (list, set)):
        skip_list = name_or_skip_list
        name = None
    else:
        skip_list = SKIP_IMDB_IDS
        name = name_or_skip_list
    # Try to extract IMDb ID from name
    imdb_from_name = None
    if name:
        m = re.search(r'(tt\d{7,8})', name)
        if m:
            imdb_from_name = m.group(1)
    check_id = imdb_from_name or imdb_id
    return check_id in skip_list if check_id else False

def get_episode_title_from_cache(ep_id: str) -> str:
    """
    Returns the episode title from media cache for the given episode IMDb ID, or empty string if not found.
    """
    if not ep_id:
        debug_print(f"[get_episode_title_from_cache] No ep_id provided.")
        return ""
    from core.media_metadata_cache import get_entry, update_entry
    entry = get_entry(ep_id)
    # debug_print(f"[get_episode_title_from_cache] Checking media cache for ep_id: {ep_id}")
    if entry and entry.get('title'):
        # debug_print(f"[get_episode_title_from_cache] Found title in media cache: {entry['title']}")
        return entry['title']
    debug_print(f"[get_episode_title_from_cache] Title not found in media cache for ep_id: {ep_id}")
    # Try manual episode cache (find the series/season/episode mapping for this ep_id)
    from core.manual_episode_cache import load_manual_episode_cache
    manual_cache = load_manual_episode_cache()
    found = False
    for series_id, seasons in manual_cache.items():
        for season, episodes in seasons.items():
            for episode, manual_ep_id in episodes.items():
                if manual_ep_id == ep_id:
                    # debug_print(f"[get_episode_title_from_cache] Found ep_id in manual cache: series={series_id}, season={season}, episode={episode}")
                    found = True
                    break
            if found:
                break
        if found:
            break
    if found:
        # If found, try to scrape OMDb info and add to media cache
        from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id
        # debug_print(f"[get_episode_title_from_cache] Scraping OMDb for ep_id: {ep_id}")
        data = fetch_title_and_year_from_imdb_id(ep_id)
        if data:
            title, year = data
            debug_print(f"[get_episode_title_from_cache] Scraped title: {title}, year: {year} for ep_id: {ep_id}")
            update_entry(ep_id, {'title': title, 'year': year})
            # Try media cache again
            entry = get_entry(ep_id)
            if entry and entry.get('title'):
                debug_print(f"[get_episode_title_from_cache] Found title in media cache after scrape: {entry['title']}")
                return entry['title']
            else:
                debug_print(f"[get_episode_title_from_cache] Title still not found in media cache after scrape for ep_id: {ep_id}")
        else:
            debug_print(f"[get_episode_title_from_cache] OMDb scrape failed for ep_id: {ep_id}")
    else:
        debug_print(f"[get_episode_title_from_cache] ep_id not found in manual cache: {ep_id}")
    # If still not found, return empty string (function promises a str return)
    debug_print(f"[get_episode_title_from_cache] Returning empty string for ep_id: {ep_id}")
    return ""
