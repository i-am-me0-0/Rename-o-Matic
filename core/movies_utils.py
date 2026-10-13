# movies_utils.py
# Utility functions for movies renamer logic
from pathlib import Path

# def clean_brackets(text: str) -> str:
#     """Remove surrounding brackets [] or () from a string if present."""
#     cleaned = text.strip()
#     if (cleaned.startswith("[") and cleaned.endswith("]")) or (cleaned.startswith("(") and cleaned.endswith("))")):
#         cleaned = cleaned[1:-1].strip()
#     return cleaned

def clean_brackets(text: str) -> str:
    """Remove surrounding brackets [] or () from a string if present."""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if (text.startswith("[") and text.endswith("]")) or (text.startswith("(") and text.endswith(")")):
        return text[1:-1].strip()
    return text

def build_new_filename(title, year, extras, imdb_id, suffix):
    filename = f"{title} ({year})"
    if extras:
        cleaned_extras = clean_brackets(extras)
        filename += f" [{cleaned_extras}]"
    if imdb_id:
        cleaned_imdb_id = clean_brackets(imdb_id)
        if cleaned_imdb_id not in filename:
            filename += f" [{cleaned_imdb_id}]"
    filename += suffix
    return filename

def get_destination_path(file: Path, folder_name: str, filename: str, MOVIES_DIR, MOVIE_FOLDER_LOCATION, CREATE_MOVIE_SUBFOLDERS):
    if CREATE_MOVIE_SUBFOLDERS:
        if MOVIE_FOLDER_LOCATION == "root":
            base_folder = MOVIES_DIR
        else:
            if file.parent.name == folder_name:
                base_folder = file.parent.parent
            else:
                base_folder = file.parent
        dest_folder = base_folder / folder_name
    else:
        dest_folder = MOVIES_DIR if MOVIE_FOLDER_LOCATION == "root" else file.parent
    return dest_folder, dest_folder / filename

from typing import Optional
def should_skip_file(dest_path: Path, file: Path) -> Optional[str]:
    if file.resolve() == dest_path.resolve():
        return f"⏭️ Already correctly named and located: {file.name}"
    if dest_path.exists() and file.resolve() != dest_path.resolve():
        return f"⏭️ File with same name already exists at destination: {dest_path.name}"
    return None

def get_title_diff(orig_title, meta_title):
    """Return the words in orig_title that are not in meta_title, preserving order."""
    if not orig_title or not meta_title:
        return orig_title or ''

    import re
    import unicodedata

    def _normalize_word(word: str) -> str:
        normalized = unicodedata.normalize("NFKD", word)
        normalized = "".join(
            char for char in normalized
            if not unicodedata.combining(char)
        )
        normalized = normalized.replace("&", "and")
        return re.sub(r"[^\w]", "", normalized).lower()

    orig_words = re.findall(r"[\w]+", str(orig_title), flags=re.UNICODE)
    meta_words = re.findall(r"[\w]+", str(meta_title), flags=re.UNICODE)
    remaining_meta = [_normalize_word(word) for word in meta_words]
    diff_words = []

    # Match title words regardless of order, but keep numeric tokens exact. A
    # source number such as 003 must remain distinct from a title number 3.
    for word in orig_words:
        normalized = _normalize_word(word)
        try:
            match_index = remaining_meta.index(normalized)
        except ValueError:
            match_index = -1
        if match_index >= 0:
            remaining_meta.pop(match_index)
        else:
            diff_words.append(word)

    return ' '.join(diff_words)


#wanted to maybe check but havent had issues much and should be even less with year validation, maybe serie episodes manually entered but don't know how to check properly
def movie_imdb_id_validation(title: str, imdb_id: str) -> bool:
    """
    Checks if the given title matches the title associated with the IMDb ID in metadata cache (or OMDb if not cached).
    Returns True if they match, False otherwise.
    """
    if not title or not imdb_id:
        return False
    from core.media_metadata_cache import get_entry
    from actions.custom_imdb_web_poster_scraper import scrape_full_movie_metadata
    meta = get_entry(imdb_id)
    if not meta:
        # Try to fetch from OMDb if not in cache
        scrape_full_movie_metadata(imdb_id)
        meta = get_entry(imdb_id)
        if not meta:
            return False
    meta_title = meta.get('title', '').strip().lower()
    input_title = title.strip().lower()
    return meta_title == input_title