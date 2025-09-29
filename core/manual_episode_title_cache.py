import json
from config import MANUAL_EPISODE_TITLE_CACHE_FILE

# This cache maps episode titles to IMDb IDs for manually entered episodes, like imdb_cache.json but for episodes.
def load_manual_episode_title_cache():
    if MANUAL_EPISODE_TITLE_CACHE_FILE.exists():
        with open(MANUAL_EPISODE_TITLE_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_manual_episode_title_cache(cache):
    if not MANUAL_EPISODE_TITLE_CACHE_FILE.parent.exists():
        MANUAL_EPISODE_TITLE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not MANUAL_EPISODE_TITLE_CACHE_FILE.exists():
        MANUAL_EPISODE_TITLE_CACHE_FILE.write_text("{}", encoding="utf-8")
    with open(MANUAL_EPISODE_TITLE_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
