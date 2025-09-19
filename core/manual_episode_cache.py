import json
from config import MANUAL_EPISODE_CACHE_FILE

def load_manual_episode_cache():
    if MANUAL_EPISODE_CACHE_FILE.exists():
        with open(MANUAL_EPISODE_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_manual_episode_cache(cache):
    with open(MANUAL_EPISODE_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
