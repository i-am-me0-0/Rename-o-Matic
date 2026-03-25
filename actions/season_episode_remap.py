from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from core.media_metadata_cache import load_metadata
from core.manual_episode_cache import load_manual_episode_cache, save_manual_episode_cache


def _to_int(value, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return default


def parse_episode_set(text: str) -> Set[int]:
    out: Set[int] = set()
    if not text:
        return out
    for token in re.split(r"[,\s]+", str(text).strip()):
        if not token:
            continue
        try:
            out.add(int(token))
        except Exception:
            continue
    return out


def parse_manual_overrides(text: str) -> Dict[int, str]:
    """Parse lines in the form `13=tt1234567` or `13: tt1234567`."""
    out: Dict[int, str] = {}
    if not text:
        return out
    for line in str(text).splitlines():
        raw = line.strip()
        if not raw:
            continue
        m = re.match(r"^(\d+)\s*[:=]\s*(tt\d{7,9})$", raw, flags=re.I)
        if not m:
            continue
        ep_num = int(m.group(1))
        imdb_id = m.group(2)
        out[ep_num] = imdb_id
    return out


def get_series_season_map(series_imdb_id: str, season: int) -> Dict[int, str]:
    """Return OMDb/media season mapping from metadata cache as {episode_num: imdb_id}."""
    data = load_metadata()
    series = data.get(str(series_imdb_id), {})
    eps = series.get("episodes", {}).get(str(season), {}) if isinstance(series, dict) else {}

    out: Dict[int, str] = {}
    if not isinstance(eps, dict):
        return out

    for ep_key, ep_val in eps.items():
        ep_num = _to_int(ep_key)
        if ep_num is None:
            continue
        if isinstance(ep_val, dict):
            imdb_id = ep_val.get("imdb_id") or ep_val.get("imdbID") or ep_val.get("id")
        else:
            imdb_id = str(ep_val) if ep_val else None
        if imdb_id and imdb_id != "N/A":
            out[ep_num] = imdb_id
    return out


def get_episode_title_map() -> Dict[str, str]:
    data = load_metadata()
    out: Dict[str, str] = {}
    for imdb_id, meta in data.items():
        if not isinstance(meta, dict):
            continue
        title = meta.get("title")
        if title:
            out[str(imdb_id)] = str(title)
    return out


def build_propagated_mapping(
    source_map: Dict[int, str],
    remove_source_episodes: Set[int],
    local_start_episode: int,
    source_start_episode: int,
    max_local_episode: Optional[int] = None,
) -> Dict[int, str]:
    """Build local episode mapping by consuming OMDb source episodes in order.

    - `remove_source_episodes` removes bad source rows before consuming.
    - mapping starts writing at `local_start_episode`.
    - source consumption starts at `source_start_episode`.
    """
    if not source_map:
        return {}

    candidates: List[Tuple[int, str]] = []
    for ep_num in sorted(source_map.keys()):
        if ep_num < source_start_episode:
            continue
        if ep_num in remove_source_episodes:
            continue
        candidates.append((ep_num, source_map[ep_num]))

    if not candidates:
        return {}

    if max_local_episode is None:
        max_local_episode = local_start_episode + len(candidates) - 1

    out: Dict[int, str] = {}
    local_ep = int(local_start_episode)
    for _, imdb_id in candidates:
        if local_ep > max_local_episode:
            break
        out[local_ep] = imdb_id
        local_ep += 1
    return out


def apply_season_remap_to_manual_cache(
    series_imdb_id: str,
    season: int,
    remap: Dict[int, str],
    manual_overrides: Optional[Dict[int, str]] = None,
    clear_existing_season: bool = False,
) -> Dict[int, str]:
    """Persist remap (+ optional explicit overrides) into manual episode cache."""
    manual_cache = load_manual_episode_cache()
    series_key = str(series_imdb_id)
    season_key = str(season)

    series_entry = manual_cache.setdefault(series_key, {})
    if clear_existing_season or season_key not in series_entry:
        series_entry[season_key] = {}

    season_entry = series_entry[season_key]

    for ep_num, imdb_id in sorted(remap.items()):
        if imdb_id:
            season_entry[str(ep_num)] = str(imdb_id)

    if manual_overrides:
        for ep_num, imdb_id in sorted(manual_overrides.items()):
            if imdb_id:
                season_entry[str(ep_num)] = str(imdb_id)

    save_manual_episode_cache(manual_cache)

    resolved: Dict[int, str] = {}
    for ep_key, imdb_id in season_entry.items():
        ep_num = _to_int(ep_key)
        if ep_num is None:
            continue
        resolved[ep_num] = str(imdb_id)
    return dict(sorted(resolved.items()))
