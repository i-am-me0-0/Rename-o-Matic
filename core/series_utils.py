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
