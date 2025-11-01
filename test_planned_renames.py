import json
import sys
from pathlib import Path
from typing import List, Dict, Any

from config import PLANNED_RENAMES_FILE, MOVIES_DIR, SERIES_DIR, debug_print

# Static lists extracted from the current `planned_renames.json` (relative to
# testLibrary/movies and testLibrary/series). Edit these lists as needed.
STATIC_MOVIES = [
    "The Matrix (1999) [1080p BluRay x264] [tt0133093].mkv",
    "Ace Ventura - Pet Detective (1994) [REMASTERED 720p BluRay x265 10Bit] [tt0109040].mkv",
    "Back to the Future (1985) [wrong id] [tt0088762] [tt0088763].mkv",
    "Elysium (2013) [720p BluRay x265 6CH] [tt1535108].mkv",
    "I, Robot (2004) [finished] [tt0343818].mkv",
    "Kung Fu Panda 3 (2016) [720p WEB-DL x265 ESub] [tt2267968].mkv",
    "Mission - Impossible - The Final Reckoning (2025) [720p - WEB-DL x265 10Bit] [tt9603208].mkv",
    "RoboCop (1987) [1980] [tt0093870].mkv",
    "RoboCop (2014) [tt1234721].mkv",
    "WALL·E (2008) [WALL-E - 720p BluRay x264] [tt0910970].mkv",
    "avatar/Avatar (2009) [Collector's Extended Edition - BluRay] [x265] [EN NL Subs] [tt0499549].mkv",
]

STATIC_SERIES = [
    "Meta Runner (2018–2022) [tt10695770]/Season 00/Meta Runner - S00E22 [Meta Runner Season 1 (Full Movie Cut) - 720p WEB-DL x265] [tt13134916].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 01/Meta Runner - S01E01 [Wrong Warp - Data Stream 720p WEB-DL x265] [tt10696624].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 01/Meta Runner - S01E02 [Out of Bounds - Game Over 720p WEB-DL x265] [tt10756490].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 02/Meta Runner - S02E01 [Hard Reset - Restart - 1080p BluRay x264] [tt13292040].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 02/Meta Runner - S02E02 [Firewall - 1080p BluRay x264] [tt13327702].mkv",
    "Scorpion (2014) [tt3514324]/Season 01/Scorpion - S01E07 [Father's Day 720p BluRay x264] [tt4089098].mkv",
    "Scorpion (2014) [tt3514324]/Season 02/Scorpion - S02E18 [The Fast & the Nerdiest 720p WEB-DL x265] [tt5376432].mkv",
    "Scorpion (2014) [tt3514324]/Season 03/Scorpion - S03E01 [E02 Civil War and More Civil War 720p WEB-DL x265] [tt5582700]].mkv",
    "Scorpion (2014) [tt3514324]/Season 03/Scorpion - S03E12 [Ice Ca-Cabes 720p WEB-DL x265] [tt6198388].mkv",
    "MacGyver (2016) [tt1399045]/Season 02/MacGyver - S02E04 [X-Ray + Penny - X-Ray and Penny 720p WEB-HD x265] [tt7234624].mkv",
    "Knight Rider (2008–2009) [tt1213404]/Season 01/Knight Rider - S01E01 [A Knight in Shining Armor - knight Pilot 720p BluRay x264] [tt1236283].mkv",
    "Knight Rider (2008–2009) [tt1213404]/Season 01/Knight Rider - S01E02 [Journey to the End of the Knight - knight 720p BluRay x264] [tt1236288].mkv",
    "Knight Rider (1982–1986) [tt0083437]/Season 01/Knight Rider - S01E01 [Knight of the Phoenix - Part 1 - Pilot 720p BluRay x264] [tt0084218].mkv",
    "Knight Rider (1982–1986) [tt0083437]/Season 01/Knight Rider - S01E02 [Knight of the Phoenix - Part 2 - Deadly Maneuvers 720p BluRay x264] [tt2388039].mkv",
    "Friends (1994) [tt0108778]/Season 02/Friends - S02E01 [The One with Ross's New Girlfriend 1900] [tt0583562].mkv",
    "Friends (1994) [tt0108778]/Season 02/Friends - S02E02 [The One with the Breast Milk 1900] [tt0583583].mkv",
    "Friends (1994) [tt0108778]/Season 01/Friends - S01E01 [The One Where Monica Gets a Roommate - 720p] [tt0583459].mkv",
    "Friends (1994) [tt0108778]/Season 01/Friends - S01E02 [The One with the Sonogram at the End - The One with the Sonogram 1900] [tt0583647].mkv",
]

# If True, print detailed per-item matches. If False, print only the concise
# summary and the 'Total matches' line. Unmatched items are always printed.
VERBOSE_DETAILS = False

# ANSI helpers (best-effort; Windows 10+ PowerShell supports these sequences).
CSI = '\x1b['
RESET = '\x1b[0m'
# BOLD = CSI + '1m'
RED = CSI + '31m'
GREEN = CSI + '32m'


def color_text(s: str, code: str) -> str:
    try:
        return f"{code}{s}{RESET}"
    except Exception:
        return s


def highlight_mismatch(a: str, b: str) -> (str, str):
    """Return (a_highlighted, b_highlighted) where the differing suffix is red.

    Uses simple common-prefix logic (case-sensitive) to find the divergence point.
    """
    if a is None:
        a = ''
    if b is None:
        b = ''
    minlen = min(len(a), len(b))
    i = 0
    while i < minlen and a[i] == b[i]:
        i += 1
    common = a[:i]
    a_rest = a[i:]
    b_rest = b[i:]
    if a_rest:
        a_h = common + color_text(a_rest, RED)
    else:
        a_h = common
    if b_rest:
        b_h = common + color_text(b_rest, RED)
    else:
        b_h = common
    return a_h, b_h


def best_candidate_and_highlight(rel: str, candidates: list) -> str:
    """Find best candidate by longest common-prefix and return a string showing
    candidate vs actual with differing part highlighted. If no candidates, return rel."""
    if not candidates:
        return rel
    best = None
    best_len = -1
    for c in candidates:
        # compute common prefix length
        L = 0
        m = min(len(rel), len(c))
        while L < m and rel[L] == c[L]:
            L += 1
        if L > best_len:
            best_len = L
            best = c
    if best is None:
        return rel
    a_h, b_h = highlight_mismatch(best, rel)
    return f"expected: {a_h}\nactual:   {b_h}"


def _strip_prefix(path_str: str, prefix: str) -> str:
    """Remove prefix from path_str if it starts with prefix. Works with POSIX-style strings."""
    if not prefix:
        return path_str
    ps = path_str.replace('\\', '/').lstrip('/')
    pref = str(prefix).replace('\\', '/').lstrip('/')
    ps_low = ps.lower()
    pref_low = pref.lower()
    if ps_low == pref_low:
        return ''
    if ps_low.startswith(pref_low + '/'):
        return ps[len(pref) + 1:]
    return ps


def check_planned_against_names(names: List[str]) -> Dict[str, Any]:
    """
    Check planned renames (PLANNED_RENAMES_FILE) against a list of provided folder/name strings.

    Matching policy (exact path-component match):
      - For each planned entry's 'to' path, strip leading MOVIES_DIR or SERIES_DIR if present.
      - Split the remaining relative path into components.
      - For each provided name (which may contain slashes), split into components and
        consider it a match iff the planned relative path's first N components exactly
        equal the provided name's components (case-insensitive).

    Returns a dict with summary and details.
    """
    # Normalize provided names into POSIX parts
    norm_names = []
    for n in names:
        if not n:
            continue
        s = n.replace('\\', '/').strip().strip('/')
        if s:
            norm_names.append(s)

    try:
        with open(PLANNED_RENAMES_FILE, 'r', encoding='utf-8') as f:
            planned = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load planned renames from {PLANNED_RENAMES_FILE}: {e}")

    movies_prefix = str(MOVIES_DIR).replace('\\', '/').rstrip('/')
    series_prefix = str(SERIES_DIR).replace('\\', '/').rstrip('/')

    matches_by_name: Dict[str, List[Dict[str, Any]]] = {n: [] for n in norm_names}
    matched_planned_indices = set()
    planned_details: List[Dict[str, Any]] = []

    for idx, item in enumerate(planned):
        to_path = item.get('to', '')
        to_posix = str(to_path).replace('\\', '/').lstrip('/')
        # strip movies/series prefix if present (handle absolute paths that contain the relative prefix)
        # Split the 'to' path into components and look for an exact component-sequence match
        parts = [p for p in to_posix.split('/') if p]
        rel = '/'.join(parts)

        matched_names = []
        for name in norm_names:
            name_parts = [p for p in name.split('/') if p]
            if not name_parts:
                continue
            found = False
            # look for the name_parts as a contiguous subsequence in parts
            for i in range(0, len(parts) - len(name_parts) + 1):
                if [pp.lower() for pp in parts[i:i + len(name_parts)]] == [np.lower() for np in name_parts]:
                    matches_by_name[name].append({'index': idx, 'item': item, 'rel': rel})
                    matched_names.append(name)
                    matched_planned_indices.add(idx)
                    found = True
                    break
            # continue to next name

        planned_details.append({'index': idx, 'item': item, 'rel': rel, 'matched_names': matched_names})

    unmatched_planned = [p for p in planned_details if p['index'] not in matched_planned_indices]
    provided_no_matches = [n for n, v in matches_by_name.items() if not v]

    summary = {
        'total_planned': len(planned),
        'provided_count': len(norm_names),
        'matched_planned_count': len(matched_planned_indices),
        'unmatched_planned_count': len(unmatched_planned),
        'provided_with_no_matches': provided_no_matches,
        'matches_by_name': matches_by_name,
        'unmatched_planned': unmatched_planned,
    }

    return summary


def run_test(names: List[str] = None) -> int:
    """CLI helper: call from command line or import and call.

    If names is None, read names from sys.argv after the module name, split by commas.
    Returns exit code 0 on success.
    """
    # Use the static movie/series lists defined above when no args provided.
    movies_to_check = STATIC_MOVIES
    series_to_check = STATIC_SERIES

    # Load planned renames
    with open(PLANNED_RENAMES_FILE, 'r', encoding='utf-8') as f:
        planned = json.load(f)

    def rel_under(to_posix: str, key: str) -> str:
        parts = [p for p in to_posix.split('/') if p]
        for i, p in enumerate(parts):
            if p.lower() == key:
                return '/'.join(parts[i+1:])
        return '/'.join(parts)

    matches_movies = {m: [] for m in movies_to_check}
    matches_series = {s: [] for s in series_to_check}
    unmatched_movies = []
    unmatched_series = []

    for idx, item in enumerate(planned):
        to_path = item.get('to', '')
        to_posix = str(to_path).replace('\\', '/').lstrip('/')
        typ = item.get('type', '').lower()
        if typ == 'movie':
            rel = rel_under(to_posix, 'movies')
            matched = False
            for m in movies_to_check:
                # exact match, case-sensitive as requested
                if rel == m:
                    matches_movies[m].append({'index': idx, 'item': item, 'rel': rel})
                    matched = True
                    break
            if not matched:
                unmatched_movies.append({'index': idx, 'item': item, 'rel': rel})
        elif typ == 'series':
            rel = rel_under(to_posix, 'series')
            matched = False
            for s in series_to_check:
                # exact match, case-sensitive
                if rel == s:
                    matches_series[s].append({'index': idx, 'item': item, 'rel': rel})
                    matched = True
                    break
            if not matched:
                unmatched_series.append({'index': idx, 'item': item, 'rel': rel})

    print(f"Total planned entries: {len(planned)}")
    print(f"Movies to check (count of provided movie names/keys to verify): {len(movies_to_check)}")
    print(f"Series to check (count of provided series names/keys to verify): {len(series_to_check)}\n")
    matched_movies_count = sum(len(v) for v in matches_movies.values())
    matched_series_count = sum(len(v) for v in matches_series.values())
    print(f"Movie entries matched: {matched_movies_count}")
    print(f"Series entries matched: {matched_series_count}")
    print(f"Total matches: {matched_movies_count + matched_series_count}\n")
    print(f"Movie entries unmatched: {len(unmatched_movies)}")
    print(f"Series entries unmatched: {len(unmatched_series)}")

    # Overall status icon
    overall_ok = (len(unmatched_movies) == 0 and len(unmatched_series) == 0)
    if overall_ok:
        print(color_text('✓ All planned entries match', GREEN))
    else:
        print(color_text('✗ Some planned entries did not match', RED))

    if unmatched_movies:
        print("Unmatched movie planned entries (sample up to 20):")
        for p in unmatched_movies[:20]:
            item = p['item']
            rel = p.get('rel')
            # show best candidate and highlight mismatch
            snippet = best_candidate_and_highlight(rel, STATIC_MOVIES)
            print(f"  - idx={p['index']} to={item.get('to')}")
            print(f"    {snippet}")
    if unmatched_series:
        print("Unmatched series planned entries (sample up to 20):")
        for p in unmatched_series[:20]:
            item = p['item']
            rel = p.get('rel')
            snippet = best_candidate_and_highlight(rel, STATIC_SERIES)
            print(f"  - idx={p['index']} to={item.get('to')}")
            print(f"    {snippet}")

    if VERBOSE_DETAILS:
        print("\nMatches by provided movie:")
        for name, matches in matches_movies.items():
            print(f"- {name}: {len(matches)} match(es)")
            for m in matches:
                it = m['item']
                print(f"    idx={m['index']} to={it.get('to')}")

        print("\nMatches by provided series:")
        for name, matches in matches_series.items():
            print(f"- {name}: {len(matches)} match(es)")
            for m in matches:
                it = m['item']
                print(f"    idx={m['index']} to={it.get('to')}")

    return 0


if __name__ == '__main__':
    # Allow direct CLI usage: pass names as comma-separated or separate args
    sys.exit(run_test())
