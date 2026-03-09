#info_extractors.py
import re
from config import EDGE_CASE_KEYWORDS, SERIES_ALIASES


def clean_extras(extras: str, keep_dots: bool = True) -> str:
    """Clean leading/trailing separators and strip wrapping parentheses.

    By default this preserves dots (periods) so the original punctuation
    can be used when composing destination filenames. Pass keep_dots=False
    when you want a version suitable for loose matching (dots -> spaces).
    """
    cleaned = extras.strip().lstrip(" -_.").strip()
    # Optionally replace dots with spaces for matching purposes
    if not keep_dots:
        cleaned = cleaned.replace('.', ' ')
    # Remove surrounding parentheses if present
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    # Remove brackets if present (new addition)
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1].strip()
    return cleaned

# def apply_series_alias(name: str) -> str:
#     """Apply alias from config if one exists."""
#     return SERIES_ALIASES.get(name, name)
def apply_series_alias(name: str) -> str:
    """Apply alias from config if one exists, matching case- and space-insensitively."""
    key = name.lower().strip()
    for alias_key, actual in SERIES_ALIASES.items():
        if alias_key.lower().strip() == key:
            return actual
    return name


def extract_movie_info(filename):
    resolution_terms = ["720p", "1080p", "2160p", "480p"]
    
    # 1. Prefer year in parentheses (standard format) - match (YYYY) first
    match_paren_year = re.match(r"^(.*?)[\s._-]*\((\d{4})\)[\s._\-]*(.*)$", filename)
    if match_paren_year:
        title = match_paren_year.group(1).strip().replace('.', ' ').replace('_', ' ')
        year = match_paren_year.group(2)
        extras = clean_extras(match_paren_year.group(3), keep_dots=False)
        return title, year, extras
    
    # 2. If filename starts with year, extract it
    match_start_year = re.match(r"^((?:19|20)\d{2})[\s._-]+(.*)$", filename)
    if match_start_year:
        year = match_start_year.group(1)
        rest = match_start_year.group(2)
        title = rest.strip().replace('.', ' ').replace('_', ' ')
        return title, year, ""

    # 3. Find all years in filename and try to use the LAST one (most likely to be release year, not part of title)
    # Pattern matches year not followed by 'p' (to avoid matching resolutions like 2160p)
    year_matches = list(re.finditer(r'(?:^|[\s._\[(-])((?:19|20)\d{2})(?!p)(?=[\s._\])\-]|$)', filename))
    
    if year_matches:
        # Try from last match backwards to find a valid year
        for match in reversed(year_matches):
            year = match.group(1)
            year_pos = match.start(1)
            
            # Split title and extras at year position
            title = filename[:year_pos].strip().replace('.', ' ').replace('_', ' ')
            extras_raw = filename[match.end():].strip()
            extras = clean_extras(extras_raw, keep_dots=False)
            
            # Verify year is not a resolution
            is_resolution = False
            for res in resolution_terms:
                if str(year) + "p" in filename:
                    is_resolution = True
                    break
            
            if not is_resolution and title:
                return title, year, extras
    
    return None, None, None


def extract_episode_info(filename):
    fname = filename.lower()

    # 1. Try to extract season/episode patterns first (always prefer explicit S/E)
    patterns = [
        r"^(.*?)\s*[-_. ]*s(\d{1,2})e(\d{1,2})[-_. ]*(.*)$",
        r"^(.*?)\s*[-_. ]*season\s*(\d{1,2})[^\d]*(?:episode)?\.?\s*(\d{1,2})?[-_. ]*(.*)?$",

        #episode regex with \b boundary should prevent resolution from being parsed as ep
        r"^(.*?)\s*[-_. ]*e(p?)(\d{1,2})[-_. ]*(.*)?$",
        r"^(.*?)\s*[-_. ]*ep(?:isode)?\.?\s*(\d{1,2})[-_. ]*(.*)?$",

        # r"^(.*?)\b[-_. ]+e(p?)(\d{1,2})\b[-_. ]*(.*)?$",
        # r"^(.*?)\b[-_. ]+ep(?:isode)?\.?\s*(\d{1,2})\b[-_. ]*(.*)?$",

     ]


    for pattern in patterns:

    # ------- trying to prevent res from ep number
    # # Common video quality tags
    # resolution_terms = ['720p', '1080p', '2160p', '480p', '30fps', '60fps']
    # contains_resolution = any(term in fname for term in resolution_terms)

    # # Prioritize specific patterns
    # patterns = [
    #     # S01E05 pattern
    #     r"^(.*?)\s*[-_. ]*s(\d{1,2})e(\d{1,2})[-_. ]*(.*)$",
        
    #     # "Season 1 Episode 2"
    #     r"^(.*?)\s*[-_. ]*season\s*(\d{1,2})[^\d]*(?:episode)?\.?\s*(\d{1,2})?[-_. ]*(.*)?$",
        
    #     # Looser episode patterns — skip if resolution is detected
    #     # These are the risky ones
    #     r"^(.*?)\b[-_. ]+e(p?)(\d{1,2})\b[-_. ]*(.*)?$",
    #     r"^(.*?)\b[-_. ]+ep(?:isode)?\.?\s*(\d{1,2})\b[-_. ]*(.*)?$",
    # ]

    # for idx, pattern in enumerate(patterns):
    #     # Skip loose episode-only patterns if resolution is detected
    #     if contains_resolution and idx >= 2:
    #         continue

        #--- end of trying to detect resolution
        match = re.match(pattern, filename, re.I)
        if match:
            groups = match.groups()
            raw_show = groups[0].strip().replace('.', ' ').replace('_', ' ')
            show = apply_series_alias(raw_show)
            season = int(groups[1]) if len(groups) > 1 and groups[1] and str(groups[1]).isdigit() else 1
            episode_raw = groups[2] if len(groups) > 2 else None
            # Robustly extract the full extras string (preserve all trailing content)
            extras = None
            try:
                if pattern == patterns[0] and len(groups) > 2 and groups[1] and groups[2]:  # SxxExx
                    extras = re.sub(rf"^{re.escape(groups[0])}\s*[-_. ]*s{groups[1]}e{groups[2]}[-_. ]*", '', filename, flags=re.I)
                elif pattern == patterns[1] and len(groups) > 2 and groups[1]:  # season xx episode xx
                    # groups[2] may be None
                    if groups[2]:
                        extras = re.sub(rf"^{re.escape(groups[0])}\s*[-_. ]*season\s*{groups[1]}[^\d]*(?:episode)?\.?\s*{groups[2]}[-_. ]*", '', filename, flags=re.I)
                    else:
                        extras = re.sub(rf"^{re.escape(groups[0])}\s*[-_. ]*season\s*{groups[1]}[^\d]*", '', filename, flags=re.I)
                elif pattern == patterns[2] and len(groups) > 2 and groups[2]:  # e(p?)xx
                    extras = re.sub(rf"^{re.escape(groups[0])}\s*[-_. ]*e(p?){groups[2]}[-_. ]*", '', filename, flags=re.I)
                elif pattern == patterns[3] and len(groups) > 2 and groups[2]:  # ep(xx)
                    extras = re.sub(rf"^{re.escape(groups[0])}\s*[-_. ]*ep(?:isode)?\.?\s*{groups[2]}[-_. ]*", '', filename, flags=re.I)
                else:
                    # fallback: use the last group if present
                    extras = groups[-1] if groups and groups[-1] else ''
            except Exception:
                extras = groups[-1] if groups and groups[-1] else ''
            extras = clean_extras(extras, keep_dots=False) if extras is not None else ''
            edge_found = any(keyword.lower() in fname for keyword in EDGE_CASE_KEYWORDS)
            episode = None
            # If episode_raw is a valid number, trust it as the episode number (do not treat as special just because of high number or resolution tags)
            if episode_raw and str(episode_raw).isdigit():
                episode = int(episode_raw)
                # For regular episodes, do NOT add edge keyword or Sxx to extras
                return show, season, episode, extras
            # If episode_raw is not a valid number and edge keyword is present, treat as special
            if edge_found:
                # Only add edge keyword if not already in extras (case-insensitive)
                for keyword in EDGE_CASE_KEYWORDS:
                    if keyword.lower() in fname:
                        kw_title = keyword.strip().title()
                        if not any(kw_title.lower() == e.strip().lower() for e in extras.split(' - ')):
                            extras = (extras + " - " + kw_title).strip() if extras else kw_title
                # Add Sxx to extras if season is present and not already in extras
                s_str = f"S{season:02}"
                if season is not None and s_str not in extras:
                    extras = (extras + " - " + s_str).strip() if extras else s_str
                return show, season, None, extras
            # If no edge keyword, but episode_raw is not a number, ignore episode
            return show, season, None, extras
    # 2. If no S/E found, check for edge keywords (like 'pilot', 'animated movie cut') as specials
    for keyword in EDGE_CASE_KEYWORDS:
        if keyword.lower() in fname:
            match = re.match(rf"^(.*?)[\s._-]*[\(]?\b{re.escape(keyword)}\b[\)]?[\s._-]*(.*)$", filename, re.I)
            if match:
                raw_show = match.group(1).strip().replace('.', ' ').replace('_', ' ')
                show = apply_series_alias(raw_show)
                extras = clean_extras(match.group(2), keep_dots=False)
                # Always add the keyword to extras if not already present
                if keyword.strip().title() not in extras:
                    extras = (keyword.strip().title() + (" " + extras if extras else "")).strip()
                return show, 0, None, extras
    # 3. Handle special case: just "Season N" or similar
    if "season" in fname:
        raw_show = filename.strip().replace('.', ' ').replace('_', ' ')
        show = apply_series_alias(raw_show)
        return show, 0, None, None
    # 4. Default fallback
    raw_show = filename.strip().replace('.', ' ').replace('_', ' ')
    show = apply_series_alias(raw_show)
    return show, None, None, None
    #     return filename.strip().replace('.', ' ').replace('_', ' '), 0, None, None

    # return filename.strip().replace('.', ' ').replace('_', ' '), None, None, None