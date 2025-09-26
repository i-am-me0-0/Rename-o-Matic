# --- Update poster cache from filenames ---
def update_posters_from_filenames(status_callback=None):
    from actions.custom_imdb_web_poster_scraper import fetch_poster_url
    from config import MOVIES_DIR, SERIES_DIR
    import re
    import requests
    from bs4 import BeautifulSoup
    cache = {}
    video_exts = {'.mkv', '.mp4', '.avi', '.mov'}
    def extract_imdb_id(text):
        match = re.search(r'(tt\d{7,9})', text)
        return match.group(1) if match else None
    print("[POSTER SCRAPER] Scanning video files...")
    files = list(Path(MOVIES_DIR).rglob('*')) + list(Path(SERIES_DIR).rglob('*'))
    print(f"[POSTER SCRAPER] Found {len(files)} files.")
    found_ids = set()
    for idx, file in enumerate(files):
        if not file.is_file() or file.suffix.lower() not in video_exts:
            continue
        print(f"[POSTER SCRAPER] ({idx+1}/{len(files)}) Processing: {file}")
        imdb_id = extract_imdb_id(file.stem)
        if not imdb_id:
            print(f"[POSTER SCRAPER] No IMDb ID found in: {file.name}")
            continue
        if imdb_id in found_ids:
            print(f"[POSTER SCRAPER] Duplicate IMDb ID: {imdb_id} (skipping)")
            continue
        found_ids.add(imdb_id)
        typ = "series" if str(SERIES_DIR) in str(file.resolve()) else "movie"
        print(f"[POSTER SCRAPER] IMDb ID: {imdb_id} | Type: {typ}")
        try:
            poster_url = fetch_poster_url(imdb_id)
            print(f"[POSTER SCRAPER] Poster URL: {poster_url}")
        except Exception as e:
            print(f"[POSTER SCRAPER] Error fetching poster URL for {imdb_id}: {e}")
            poster_url = None
        title = ""
        try:
            url = f"https://www.imdb.com/title/{imdb_id}/"
            headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                meta = soup.find("meta", property="og:title")
                if meta and meta.get("content"):
                    title = meta["content"].replace(" - IMDb", "").strip()
            print(f"[POSTER SCRAPER] Title: {title}")
        except Exception as e:
            print(f"[POSTER SCRAPER] Error fetching title for {imdb_id}: {e}")
        cache[imdb_id] = {
            "title": title,
            "type": typ,
            "poster_url": poster_url or ""
        }
    cache_path = Path(__file__).parent.parent / "cache" / "poster_url_cache.json"
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        print(f"[POSTER SCRAPER] Updated poster_url_cache.json with {len(cache)} entries.")
        if status_callback:
            status_callback(f"Updated poster_url_cache.json with {len(cache)} entries.")
    except Exception as e:
        print(f"[POSTER SCRAPER] Error writing cache: {e}")
        if status_callback:
            status_callback(f"Error writing cache: {e}")
# core/poster_scraper.py
"""
Poster scraping and downloading logic for movies, series, and episodes.
"""
import re
import json
from pathlib import Path
from actions.custom_imdb_web_poster_scraper import download_image
from config import MOVIES_DIR, SERIES_DIR

video_exts = {'.mkv', '.mp4', '.avi', '.mov'}

def extract_imdb_id(text):
    match = re.search(r'(tt\d{7,9})', text)
    return match.group(1) if match else None

def download_images_from_poster_cache(cache_path=None, status_callback=None):
    """
    Scan all movie, series, and episode files/folders.
    Download missing posters/thumbnails using poster_url_cache.json.
    """
    if cache_path is None:
        cache_path = Path(__file__).parent.parent / "cache" / "poster_url_cache.json"
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception as e:
        print(f"[POSTER SCRAPER] Error reading cache: {e}")
        if status_callback:
            status_callback(f"Error reading cache: {e}")
        return 0
    count = 0
    # Movies
    print("[POSTER SCRAPER] Scanning movie files for missing posters...")
    for file in Path(MOVIES_DIR).rglob('*'):
        if not file.is_file() or file.suffix.lower() not in video_exts:
            continue
        imdb_id = extract_imdb_id(file.stem)
        if not imdb_id:
            continue
        poster_path = file.parent / f"{file.stem}-poster.jpg"
        if poster_path.exists():
            continue
        entry = cache.get(imdb_id)
        if not entry or not entry.get("poster_url"):
            print(f"[POSTER SCRAPER] No poster URL in cache for {imdb_id}")
            continue
        url = entry["poster_url"]
        print(f"[POSTER SCRAPER] Downloading movie poster for {imdb_id} to {poster_path}")
        result = download_image(url, poster_path)
        print(f"[POSTER SCRAPER] Download result: {result}")
        if result:
            count += 1
    # Series
    print("[POSTER SCRAPER] Scanning series folders for missing posters...")
    for folder in Path(SERIES_DIR).rglob('*'):
        if not folder.is_dir():
            continue
        imdb_id = extract_imdb_id(folder.name)
        if not imdb_id:
            continue
        poster_path = folder / "poster.jpg"
        if poster_path.exists():
            continue
        entry = cache.get(imdb_id)
        if not entry or not entry.get("poster_url"):
            print(f"[POSTER SCRAPER] No poster URL in cache for {imdb_id}")
            continue
        url = entry["poster_url"]
        print(f"[POSTER SCRAPER] Downloading series poster for {imdb_id} to {poster_path}")
        result = download_image(url, poster_path)
        print(f"[POSTER SCRAPER] Download result: {result}")
        if result:
            count += 1
    # Episodes
    print("[POSTER SCRAPER] Scanning episode files for missing thumbnails...")
    for file in Path(SERIES_DIR).rglob('*'):
        if not file.is_file() or file.suffix.lower() not in video_exts:
            continue
        imdb_id = extract_imdb_id(file.stem)
        if not imdb_id:
            continue
        thumb_path = file.parent / f"{file.stem}-thumb.jpg"
        if thumb_path.exists():
            continue
        entry = cache.get(imdb_id)
        if not entry or not entry.get("poster_url"):
            print(f"[POSTER SCRAPER] No poster URL in cache for {imdb_id}")
            continue
        url = entry["poster_url"]
        print(f"[POSTER SCRAPER] Downloading episode thumbnail for {imdb_id} to {thumb_path}")
        result = download_image(url, thumb_path)
        print(f"[POSTER SCRAPER] Download result: {result}")
        if result:
            count += 1
    print(f"[POSTER SCRAPER] Downloaded {count} images from poster_url_cache.json.")
    if status_callback:
        status_callback(f"Downloaded {count} images from poster_url_cache.json.")
    return count
