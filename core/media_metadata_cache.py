import json
import threading
import queue
import os
from typing import Optional, Dict, Any, cast
from config import MEDIA_METADATA_FILE  


_metadata_cache: Optional[Dict[str, Any]] = None
# Background writer queue and thread for non-blocking saves
_write_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
_writer_thread_started = False
_writer_lock = threading.Lock()

def load_metadata() -> Dict[str, Any]:
    """
    Load metadata from disk into an in-memory cache on first access.
    Subsequent calls return the cached dict to avoid repeated blocking JSON loads
    on the GUI thread. This keeps behaviour backwards compatible while making
    repeated lookups (get_entry/update_entry) fast.
    """
    global _metadata_cache
    if _metadata_cache is not None:
        return cast(Dict[str, Any], _metadata_cache)
    if not MEDIA_METADATA_FILE.exists():
        _metadata_cache = {}
        return _metadata_cache
    try:
        with open(MEDIA_METADATA_FILE, 'r', encoding='utf-8') as f:
            _metadata_cache = json.load(f)
            return cast(Dict[str, Any], _metadata_cache)
    except Exception:
        _metadata_cache = {}
        return cast(Dict[str, Any], _metadata_cache)

def save_metadata(data: Dict[str, Any]):
    """
    Queue the metadata for background writing and update the in-memory cache.

    The background writer thread will coalesce rapid successive snapshots and
    write only the most recent data to disk, using an atomic tempfile+replace
    strategy to avoid corrupt files.
    """
    global _metadata_cache, _writer_thread_started
    # Ensure cache dir exists
    if not MEDIA_METADATA_FILE.parent.exists():
        MEDIA_METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Update in-memory cache immediately so readers see latest state
    _metadata_cache = data

    # Start writer thread once
    with _writer_lock:
        if not _writer_thread_started:
            t = threading.Thread(target=_background_writer, daemon=True)
            t.start()
            _writer_thread_started = True

    # Put the latest snapshot on the queue for writing
    try:
        _write_queue.put_nowait(data)
    except Exception:
        # If the queue is full or otherwise fails, fall back to synchronous write
        try:
            tmp_path = MEDIA_METADATA_FILE.with_suffix('.tmp')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.replace(tmp_path, MEDIA_METADATA_FILE)
            except Exception:
                tmp_path.rename(MEDIA_METADATA_FILE)
        except Exception:
            pass


def flush_metadata(data: Optional[Dict[str, Any]] = None) -> bool:
    """Synchronously flush metadata and close the temporary file before returning."""
    global _metadata_cache
    snapshot = data if isinstance(data, dict) else load_metadata()
    _metadata_cache = snapshot

    if not MEDIA_METADATA_FILE.parent.exists():
        MEDIA_METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = MEDIA_METADATA_FILE.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, MEDIA_METADATA_FILE)
        return True
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False

def _background_writer():
    """Background thread that writes the most recent metadata snapshot to disk.

    It coalesces queued snapshots so that if multiple updates arrive quickly,
    only the last one is written, avoiding excessive disk churn.
    """
    while True:
        try:
            data = _write_queue.get()  # block until at least one item
            # Drain the queue to get the most recent update
            try:
                while True:
                    data = _write_queue.get_nowait()
            except Exception:
                pass

            try:
                tmp_path = MEDIA_METADATA_FILE.with_suffix('.tmp')
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                try:
                    os.replace(tmp_path, MEDIA_METADATA_FILE)
                except Exception:
                    try:
                        tmp_path.rename(MEDIA_METADATA_FILE)
                    except Exception:
                        pass
            except Exception:
                # ignore write errors; best-effort only
                pass
        except Exception:
            # Keep the writer alive on unexpected errors
            continue

def clear_metadata_cache():
    """Clear the in-memory metadata cache (useful for debugging)."""
    global _metadata_cache
    _metadata_cache = None

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
        # Preserve poster_url and summary if they exist in the old data
        existing = data.get(episode_id, {})
        if existing:
            # Copy poster_url and summary from existing entry if present and new data doesn't have them
            if existing.get('poster_url') and not episode_data.get('poster_url'):
                episode_data['poster_url'] = existing['poster_url']
            if existing.get('summary') and not episode_data.get('summary'):
                episode_data['summary'] = existing['summary']
        # Now overwrite with the merged data
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