# core/file_lister.py
from pathlib import Path
from config import MOVIES_DIR, SERIES_DIR, VIDEO_EXTENSIONS

def list_movie_files():
    """Return a list of all movie files with metadata."""
    files = []
    for file in MOVIES_DIR.rglob("*"):
        if file.suffix.lower() in VIDEO_EXTENSIONS:
            files.append({
                "path": file,
                "type": "movie"
            })
    return files

def list_series_files():
    """Return a list of all series episode files with metadata."""
    files = []
    for file in SERIES_DIR.rglob("*"):
        if file.suffix.lower() in VIDEO_EXTENSIONS:
            files.append({
                "path": file,
                "type": "series"
            })
    return files

def list_all_media_files():
    return list_movie_files() + list_series_files()
