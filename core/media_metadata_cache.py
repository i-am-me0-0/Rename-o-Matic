import json
from pathlib import Path
from typing import Optional, Dict, Any
from config import MEDIA_METADATA_FILE 


def load_metadata() -> Dict[str, Any]:
    if not MEDIA_METADATA_FILE.exists():
        return {}
    try:
        with open(MEDIA_METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_metadata(data: Dict[str, Any]):
    with open(MEDIA_METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_entry(imdb_id: str) -> Optional[Dict[str, Any]]:
    data = load_metadata()
    return data.get(imdb_id)

def set_entry(imdb_id: str, entry: Dict[str, Any]):
    data = load_metadata()
    data[imdb_id] = entry
    save_metadata(data)

def update_entry(imdb_id: str, updates: Dict[str, Any]):
    data = load_metadata()
    entry = data.get(imdb_id, {})
    entry.update(updates)
    data[imdb_id] = entry
    save_metadata(data)

# def add_episode_to_series(series_id: str, season: str, episode: str, episode_id: str, episode_data: Dict[str, Any]):
#     data = load_metadata()
#     series = data.setdefault(series_id, {})
#     if 'episodes' not in series:
#         series['episodes'] = {}
#     if season not in series['episodes']:
#         series['episodes'][season] = {}
#     series['episodes'][season][episode] = episode_id
#     # Also add episode metadata as its own entry
#     data[episode_id] = episode_data
#     save_metadata(data)
def add_episode_to_series(series_id: str, season: str, episode: str, episode_id: str, episode_data: Dict[str, Any]):
    data = load_metadata()
    series = data.setdefault(series_id, {})
    if 'episodes' not in series:
        series['episodes'] = {}
    if season not in series['episodes']:
        series['episodes'][season] = {}
    series['episodes'][season][episode] = episode_id
    # Also add episode metadata as its own entry
    if episode_id and episode_data:
        data[episode_id] = episode_data
    save_metadata(data)

def get_episode_id_from_metadata(series_id: str, season: str, episode: str) -> Optional[str]:
    data = load_metadata()
    series = data.get(series_id, {})
    episodes = series.get('episodes', {})
    return episodes.get(season, {}).get(episode)

def get_episode_info_by_id(episode_imdb_id: str) -> Optional[Dict[str, Any]]:
    """
    Return (series_id, season, episode, series_title, episode_title) for a given episode IMDb ID, if present in metadata.
    """
    data = load_metadata()
    for series_id, series in data.items():
        episodes = series.get('episodes', {})
        for season, eps in episodes.items():
            for ep_num, ep_id in eps.items():
                if ep_id == episode_imdb_id:
                    return {
                        'series_id': series_id,
                        'season': season,
                        'episode': ep_num,
                        'series_title': series.get('title'),
                        'episode_title': data.get(ep_id, {}).get('title')
                    }
    return None