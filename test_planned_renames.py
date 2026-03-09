import json
import sys
import difflib
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import re

from config import PLANNED_RENAMES_FILE, MOVIES_DIR, SERIES_DIR, debug_print

# Static lists extracted from the current `planned_renames.json` (relative to
# testLibrary/movies and testLibrary/series). Edit these lists as needed.
STATIC_MOVIES = [
    "2001 - A Space Odyssey (1968) [REMASTERED 720p BluRay x265 10Bit] [tt0062622].mkv",
    "Naked Gun 33 1-3 - The Final Insult (1994) [720p BluRay x265 10Bit] [tt0110622].mkv",
    "The Matrix (1999) [1080p BluRay x264] [tt0133093].mkv",
    "Ace Ventura - Pet Detective (1994) [REMASTERED 720p BluRay x265 10Bit] [tt0109040].mkv",
    "Back to the Future (1985) [wrong id tt0088762] [tt0088763].mkv",
    "Limitless (2011) [2000 - 0] [tt1219289].mkv",
    "Elysium (2013) [720p BluRay x265 6CH] [tt1535108].mkv",
    "Blade Runner 2049 (2017) [720p BluRay x265] [tt1856101].mkv",
    "I, Robot (2004) [finished] [tt0343818].mkv",
    "Kung Fu Panda 3 (2016) [720p WEB-DL x265 ESub] [tt2267968].mkv",
    "Mission - Impossible - The Final Reckoning (2025) [720p - WEB-DL x265 10Bit] [tt9603208].mkv",
    "RoboCop (1987) [1980] [tt0093870].mkv",
    "RoboCop (2014) [tt1234721].mkv",
    "WALL·E (2008) [720p BluRay x264] [tt0910970].mkv",
    "avatar/Avatar (2009) [Collector's Extended Edition - BluRay x265 EN NL Subs] [tt0499549].mkv",
]

STATIC_SERIES = [
    "Reacher (2022–) [tt9288030]/Season 03/Reacher - S03E07 [L.A. Story 720p WEB-DL x265 10Bit] [tt34929210].mkv",
    "DuckTales (2017–2021) [tt5531466]/Season 01/DuckTales - S01E11 [Beware the B.U.D.D.Y. System! 720p WEB-HD x264] [tt8228740].mkv",
    "DuckTales (2017–2021) [tt5531466]/Season 01/DuckTales - S01E17 [From the Confidental Casefiles of Agent 22! - From the Confidential Casefiles of Agent 22 720p WEB-HD x264] [tt8373296].mkv",
    "DuckTales (2017–2021) [tt5531466]/Season 02/DuckTales - S02E07 [Whatever Happened to Della Duck! 720p WEB-HD x264] [tt9313942].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 00/Meta Runner - S00E22 [Meta Runner Season 1 (Full Movie Cut) - 720p WEB-DL x265] [tt13134916].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 01/Meta Runner - S01E01 [Wrong Warp - Data Stream 720p WEB-DL x265] [tt10696624].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 01/Meta Runner - S01E02 [Out of Bounds - Game Over 720p WEB-DL x265] [tt10756490].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 02/Meta Runner - S02E01 [Hard Reset - Restart - 1080p BluRay x264] [tt13292040].mkv",
    "Meta Runner (2018–2022) [tt10695770]/Season 02/Meta Runner - S02E02 [Firewall - 1080p BluRay x264] [tt13327702].mkv",
    "Limitless (2015–2016) [tt4422836]/Season 01/Limitless - S01E01 [tt4927052].mkv",
    "Scorpion (2014–2018) [tt3514324]/Season 01/Scorpion - S01E07 [Father's Day 720p BluRay x264] [tt4089098].mkv",
    "Scorpion (2014–2018) [tt3514324]/Season 02/Scorpion - S02E18 [The Fast & the Nerdiest 720p WEB-DL x265] [tt5376432].mkv",
    "Scorpion (2014–2018) [tt3514324]/Season 03/Scorpion - S03E01 [E02 Civil War and More Civil War 720p WEB-DL x265] [tt5582700]].mkv",
    "Scorpion (2014–2018) [tt3514324]/Season 03/Scorpion - S03E12 [Ice Ca-Cabes 720p WEB-DL x265] [tt6198388].mkv",
    "MacGyver (2016–2021) [tt1399045]/Season 02/MacGyver - S02E04 [X-Ray + Penny - X-Ray and Penny 720p WEB-HD x265] [tt7234624].mkv",
    "Knight Rider (2008–2009) [tt1213404]/Season 01/Knight Rider - S01E01 [A Knight in Shining Armor - knight Pilot 720p BluRay x264] [tt1236283].mkv",
    "Knight Rider (2008–2009) [tt1213404]/Season 01/Knight Rider - S01E02 [Journey to the End of the Knight - knight 720p BluRay x264] [tt1236288].mkv",
    "Knight Rider (1982–1986) [tt0083437]/Season 01/Knight Rider - S01E01 [Knight of the Phoenix - Part 1 - Pilot 720p BluRay x264] [tt0084218].mkv",
    "Knight Rider (1982–1986) [tt0083437]/Season 01/Knight Rider - S01E02 [Knight of the Phoenix - Part 2 - Deadly Maneuvers 720p BluRay x264] [tt2388039].mkv",
    "Friends (1994–2004) [tt0108778]/Season 02/Friends - S02E01 [The One with Ross's New Girlfriend 1900] [tt0583562].mkv",
    "Friends (1994–2004) [tt0108778]/Season 02/Friends - S02E02 [The One with the Breast Milk 1900] [tt0583583].mkv",
    "Friends (1994–2004) [tt0108778]/Season 01/Friends - S01E01 [The One Where Monica Gets a Roommate - 720p] [tt0583459].mkv",
    "Friends (1994–2004) [tt0108778]/Season 01/Friends - S01E02 [The One with the Sonogram at the End - The One with the Sonogram 1900] [tt0583647].mkv",
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


def highlight_mismatch(a: str, b: str) -> Tuple[str, str]:
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
    # Prefer highest similarity ratio (difflib). Tiebreaker: longest common prefix.
    best = None
    best_score = -1.0
    best_prefix = -1
    for c in candidates:
        try:
            score = difflib.SequenceMatcher(None, rel, c).ratio()
        except Exception:
            score = 0.0
        # compute common prefix length as tiebreaker
        L = 0
        m = min(len(rel), len(c))
        while L < m and rel[L] == c[L]:
            L += 1
        if score > best_score or (abs(score - best_score) < 1e-9 and L > best_prefix):
            best_score = score
            best = c
            best_prefix = L
    if best is None:
        return rel
    a_h, b_h = highlight_mismatch(best, rel)
    return f"expected: {a_h}\nactual:   {b_h}"


def best_candidate_raw(rel: str, candidates: list) -> str:
    """Return the single best candidate string (no highlighting). Uses difflib ratio + prefix tiebreaker."""
    if not candidates:
        return ''
    best = None
    best_score = -1.0
    best_prefix = -1
    for c in candidates:
        try:
            score = difflib.SequenceMatcher(None, rel, c).ratio()
        except Exception:
            score = 0.0
        L = 0
        m = min(len(rel), len(c))
        while L < m and rel[L] == c[L]:
            L += 1
        if score > best_score or (abs(score - best_score) < 1e-9 and L > best_prefix):
            best_score = score
            best = c
            best_prefix = L
    return best or ''


def word_diff_highlight(expected: str, actual: str) -> Tuple[str, str]:
    """Return (expected_h, actual_h) where only differing words are colored red.

    Uses difflib.ndiff on word tokens; equal words are left as-is, words present only
    in expected are colored in the expected string, words present only in actual are
    colored in the actual string.
    """
    exp_words = re.findall(r"\S+", expected)
    act_words = re.findall(r"\S+", actual)
    diff = list(difflib.ndiff(exp_words, act_words))
    exp_out = []
    act_out = []
    for line in diff:
        code = line[:2]
        token = line[2:]
        if code == '  ':
            exp_out.append(token)
            act_out.append(token)
        elif code == '- ':
            exp_out.append(color_text(token, RED))
        elif code == '+ ':
            act_out.append(color_text(token, RED))
    return ' '.join(exp_out), ' '.join(act_out)


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


def run_test(names: Optional[List[str]] = None) -> int:
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
        # 1) exact component match (e.g. 'series' or 'movies')
        for i, p in enumerate(parts):
            if p.lower() == key:
                return '/'.join(parts[i+1:])
        # 2) try to strip known configured prefix (MOVIES_DIR / SERIES_DIR)
        try:
            pref = SERIES_DIR if key == 'series' else MOVIES_DIR
            pref_norm = str(pref).replace('\\', '/').lstrip('/').lower()
            tp = to_posix.replace('\\', '/').lstrip('/')
            if tp.lower().startswith(pref_norm + '/'):
                return tp[len(pref_norm) + 1:]
        except Exception:
            pass
        # 3) fallback: if a path segment contains the keyword (e.g. '.series'), strip from there
        for i, p in enumerate(parts):
            if key in p.lower():
                return '/'.join(parts[i+1:])
        # 4) give up and return joined parts
        return '/'.join(parts)

    matches_movies = {m: [] for m in movies_to_check}
    matches_series = {s: [] for s in series_to_check}
    unmatched_movies = []
    unmatched_series = []

    # Phase 1: build candidate lists for each planned entry (exact component-wise contiguous match)
    movie_candidates_per_planned: Dict[int, List[str]] = {}
    series_candidates_per_planned: Dict[int, List[str]] = {}

    for idx, item in enumerate(planned):
        to_path = item.get('to', '')
        to_posix = str(to_path).replace('\\', '/').lstrip('/')
        typ = item.get('type', '').lower()
        if typ == 'movie':
            rel = rel_under(to_posix, 'movies')
            rel_parts = [p for p in rel.split('/') if p]
            cands: List[str] = []
            for m in movies_to_check:
                m_parts = [p for p in m.replace('\\', '/').split('/') if p]
                if not m_parts:
                    continue
                matched_flag = False
                for i in range(0, len(rel_parts) - len(m_parts) + 1):
                    if rel_parts[i:i + len(m_parts)] == m_parts:
                        cands.append(m)
                        matched_flag = True
                        break
                if VERBOSE_DETAILS:
                    status = 'MATCH' if matched_flag else 'no'
                    print(f"[verbose] planned idx={idx} movie_rel='{rel}' compared to provided='{m}' -> {status}")
            movie_candidates_per_planned[idx] = cands
        elif typ == 'series':
            rel = rel_under(to_posix, 'series')
            rel_parts = [p for p in rel.split('/') if p]
            cands: List[str] = []
            for s in series_to_check:
                s_parts = [p for p in s.replace('\\', '/').split('/') if p]
                if not s_parts:
                    continue
                matched_flag = False
                for i in range(0, len(rel_parts) - len(s_parts) + 1):
                    if rel_parts[i:i + len(s_parts)] == s_parts:
                        cands.append(s)
                        matched_flag = True
                        break
                if VERBOSE_DETAILS:
                    status = 'MATCH' if matched_flag else 'no'
                    print(f"[verbose] planned idx={idx} series_rel='{rel}' compared to provided='{s}' -> {status}")
            series_candidates_per_planned[idx] = cands

    # Helper: common prefix length for tie-breaking
    def common_prefix_len(a: str, b: str) -> int:
        m = min(len(a), len(b))
        i = 0
        while i < m and a[i] == b[i]:
            i += 1
        return i

    # Assignment: use maximum bipartite matching (Kuhn) so each provided name can be used at most once
    def max_bipartite_assign(candidates_per_planned: Dict[int, List[str]],
                             provided_list: List[str],
                             strip_key: str) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
        # Map provided names to indices
        prov_index = {p: i for i, p in enumerate(provided_list)}
        n_prov = len(provided_list)

        # Build adjacency: for each planned idx -> list of prov indices
        adj: Dict[int, List[int]] = {}
        for idx, cands in candidates_per_planned.items():
            adj[idx] = [prov_index[c] for c in cands if c in prov_index]

        # Kuhn (DFS) for maximum matching
        prov_match = [-1] * n_prov  # prov_match[j] = planned_idx assigned to provided j

        def try_khun(u: int, seen: List[bool]) -> bool:
            for v in adj.get(u, []):
                if seen[v]:
                    continue
                seen[v] = True
                if prov_match[v] == -1 or try_khun(prov_match[v], seen):
                    prov_match[v] = u
                    return True
            return False

        # attempt to match each planned node
        for u in list(adj.keys()):
            seen = [False] * n_prov
            try_khun(u, seen)

        # Build assigned_by_provided and unmatched lists
        assigned_by_provided: Dict[str, List[Dict[str, Any]]] = {p: [] for p in provided_list}
        matched_planned = set()

        for prov, p_idx in enumerate(prov_match):
            if p_idx != -1:
                pname = provided_list[prov]
                item = planned[p_idx]
                to_path = item.get('to', '')
                rel = rel_under(str(to_path).replace('\\', '/').lstrip('/'), strip_key)
                assigned_by_provided[pname].append({'index': p_idx, 'item': item, 'rel': rel})
                matched_planned.add(p_idx)

        unmatched: List[Dict[str, Any]] = []
        # Only consider planned indices that were part of this candidates_per_planned (same type)
        for idx in candidates_per_planned.keys():
            if idx in matched_planned:
                continue
            item = planned[idx]
            to_path = item.get('to', '')
            rel = rel_under(str(to_path).replace('\\', '/').lstrip('/'), strip_key)
            # include candidate list for diagnostics
            cands = candidates_per_planned.get(idx, [])
            unmatched.append({'index': idx, 'item': item, 'rel': rel, 'candidates': cands})

        return assigned_by_provided, unmatched

    # Do assignments using bipartite matching
    assigned_movies, unmatched_movies = max_bipartite_assign(movie_candidates_per_planned, movies_to_check, 'movies')
    assigned_series, unmatched_series = max_bipartite_assign(series_candidates_per_planned, series_to_check, 'series')

    matches_movies = assigned_movies
    matches_series = assigned_series

    # Print only concise unmatched info (less noisy): show planned filename and closest expected key
    def print_unmatched_list(unmatched_list, static_list, kind_label: str):
        if not unmatched_list:
            return
        emoji = '🔴'
        print(f"\n{emoji} Unmatched {kind_label} entries ({len(unmatched_list)}):")
        for p in unmatched_list:
            item = p['item']
            rel = p.get('rel') or ''
            planned_full = item.get('to')
            candidates = p.get('candidates', [])
            closest = best_candidate_raw(rel, static_list) if candidates else ''
            # concise colored output: Planned (red), Closest expected (green)
            planned_line = color_text(f"Planned: {planned_full}", RED)
            if closest:
                expected_line = color_text(f"Expected (closest): {closest}", GREEN)
            else:
                expected_line = color_text("Expected (closest): <none>", RED)
            print(f"  - idx={p['index']} {planned_line}")
            print(f"    {expected_line}")

    # Movies then series: print a compact validation summary + unmatched details with word diffs
    matched_movies_count = sum(len(v) for v in matches_movies.values())
    matched_series_count = sum(len(v) for v in matches_series.values())
    total_matches = matched_movies_count + matched_series_count

    icon = ""
    if total_matches == len(planned):
        icon = "✅"
    else: 
        icon = "❌"

    print("\n--------Validation Summary--------------")
    print(f"Planned entries: {len(planned)}")
    print(f"Movies checked: {len(movies_to_check)}\t✅ Matches: {matched_movies_count}\t❌ Unmatched: {len(unmatched_movies)}")
    print(f"Series checked: {len(series_to_check)}\t✅ Matches: {matched_series_count}\t❌ Unmatched: {len(unmatched_series)}")
    print(f"Overall matches: {total_matches} / {len(planned)} {icon}\n")

    # Unmatched details (series then movies)
    if unmatched_series:
        print(f"------Unmatched Series ({len(unmatched_series)})---------")
        for p in unmatched_series:
            rel = p.get('rel') or ''
            planned_full = p['item'].get('to')
            expected = best_candidate_raw(rel, STATIC_SERIES) or ''
            # remove leading testLibrary/... if present in planned_full for display
            actual = rel
            exp_h, act_h = word_diff_highlight(expected, actual)
            print(f"expected: {exp_h}")
            print(f"actual:   {act_h}\n")

    if unmatched_movies:
        print(f"------Unmatched Movies ({len(unmatched_movies)})---------")
        for p in unmatched_movies:
            rel = p.get('rel') or ''
            planned_full = p['item'].get('to')
            expected = best_candidate_raw(rel, STATIC_MOVIES) or ''
            actual = rel
            exp_h, act_h = word_diff_highlight(expected, actual)
            print(f"expected: {exp_h}")
            print(f"actual:   {act_h}\n")

    # Overall status icon
    overall_ok = (len(unmatched_movies) == 0 and len(unmatched_series) == 0)
    if overall_ok:
        print(color_text('✓ All planned entries match', GREEN))
    else:
        print(color_text('✗ Some planned entries did not match', RED))

    # (Detailed per-unmatched listing removed; compact validation summary above is used.)

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
