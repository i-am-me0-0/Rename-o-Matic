# movies_utils.py
# Utility functions for movies renamer logic
from pathlib import Path
import difflib

def clean_brackets(text: str) -> str:
    """Remove surrounding brackets [] or () from a string if present."""
    cleaned = text.strip()
    if (cleaned.startswith("[") and cleaned.endswith("]")) or (cleaned.startswith("(") and cleaned.endswith("))")):
        cleaned = cleaned[1:-1].strip()
    return cleaned

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
    orig_words = orig_title.split()
    meta_words = meta_title.split()
    # Use SequenceMatcher to find matching blocks
    sm = difflib.SequenceMatcher(None, orig_words, meta_words)
    diff_words = []
    opcodes = sm.get_opcodes()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'delete' or tag == 'replace':
            diff_words.extend(orig_words[i1:i2])
    return ' '.join(diff_words)
