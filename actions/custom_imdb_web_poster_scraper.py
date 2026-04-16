

#custom_imdb_web_poster_scraper.py
import time
import random
import requests
from bs4 import BeautifulSoup
from typing import List, Optional 
import os
import re
import json
from pathlib import Path
from config import MOVIES_DIR, SERIES_DIR, USER_AGENTS
#, SCRAPE_MOVIE_POSTERS, SCRAPE_SERIES_THUMBNAILS, SCRAPE_SERIES_ROOT_FOLDERS
from core.media_metadata_cache import update_entry, get_entry

BASE_URL = "https://www.imdb.com/title/{imdb_id}/"
session = requests.Session()


def _normalize_poster_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    normalized = str(url).strip().replace('\\/', '/')
    if normalized.startswith('//'):
        normalized = 'https:' + normalized
    if normalized.startswith('http://'):
        normalized = 'https://' + normalized[len('http://'):]
    return normalized if normalized.startswith('https://') else None


def _extract_poster_url_from_html(html: str) -> Optional[str]:
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Most reliable path when IMDb returns the canonical title page.
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        return _normalize_poster_url(str(meta.get("content")))

    twitter_meta = soup.find("meta", attrs={"name": "twitter:image"})
    if twitter_meta and twitter_meta.get("content"):
        return _normalize_poster_url(str(twitter_meta.get("content")))

    for selector in (".ipc-media img", "img.ipc-image", "img[src*='m.media-amazon.com']"):
        img = soup.select_one(selector)
        if img and img.get("src"):
            normalized = _normalize_poster_url(str(img.get("src")))
            if normalized:
                return normalized

    # Fallback: parse JSON-LD blobs and embedded script text for image fields.
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
            nodes = payload if isinstance(payload, list) else [payload]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                image_field = node.get("image") or node.get("thumbnailUrl")
                if isinstance(image_field, str):
                    normalized = _normalize_poster_url(image_field)
                    if normalized:
                        return normalized
                elif isinstance(image_field, list):
                    for image_item in image_field:
                        normalized = _normalize_poster_url(str(image_item))
                        if normalized:
                            return normalized
                elif isinstance(image_field, dict):
                    normalized = _normalize_poster_url(
                        image_field.get("url") or image_field.get("contentUrl")
                    )
                    if normalized:
                        return normalized
        except Exception:
            pass

        match = re.search(r'"(?:image|thumbnailUrl)"\s*:\s*"(https?://[^"\\]+)"', raw)
        if match:
            normalized = _normalize_poster_url(match.group(1))
            if normalized:
                return normalized

    return None


def _fetch_poster_from_suggestion_api(imdb_id: str) -> Optional[str]:
    try:
        first = imdb_id[0].lower() if imdb_id else "t"
        suggestion_url = f"https://v3.sg.media-imdb.com/suggestion/{first}/{imdb_id}.json"
        resp = requests.get(suggestion_url, timeout=10)
        if resp.status_code != 200:
            return None
        payload = resp.json()
        for item in payload.get("d", []):
            if str(item.get("id", "")).lower() != imdb_id.lower():
                continue
            image_obj = item.get("i")
            if isinstance(image_obj, dict):
                poster_url = image_obj.get("imageUrl") or image_obj.get("url")
                normalized = _normalize_poster_url(poster_url if isinstance(poster_url, str) else None)
                if normalized:
                    return normalized
        return None
    except Exception:
        return None


def fetch_poster_url(imdb_id: str) -> Optional[str]:
    urls = [
        BASE_URL.format(imdb_id=imdb_id),
        BASE_URL.format(imdb_id=imdb_id) + "reference/",
    ]
    transient_statuses = {202, 429, 500, 502, 503, 504}
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.imdb.com/",
    }
    last_status = None
    last_exception = None

    for url in urls:
        for attempt in range(1, 4):
            try:
                response = session.get(url, headers=headers, timeout=10)
                last_status = response.status_code
                poster_url = _extract_poster_url_from_html(response.text)
                if poster_url:
                    return poster_url

                if response.status_code in transient_statuses and attempt < 3:
                    # IMDb sometimes returns temporary responses (like 202); back off and retry.
                    time.sleep((0.35 * attempt) + random.uniform(0.1, 0.4))
                    continue
                break
            except Exception as e:
                last_exception = e
                if attempt < 3:
                    time.sleep((0.35 * attempt) + random.uniform(0.1, 0.4))
                    continue
                break

    suggestion_poster = _fetch_poster_from_suggestion_api(imdb_id)
    if suggestion_poster:
        return suggestion_poster

    if last_status is not None:
        print(f"[{imdb_id}] Failed with status {last_status}")
    elif last_exception is not None:
        print(f"[{imdb_id}] Error: {last_exception}")

    return None


def download_image(url: str, save_path: Path) -> bool:
    if save_path.exists() and save_path.stat().st_size > 0:
        print(f"📁 Already exists: {save_path.name}")
        return True

    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            print(f"💾 Saved image as {save_path.name}")
            return True
        else:
            print(f"Failed to download image. HTTP {response.status_code}")
    except Exception as e:
        print(f"Error downloading image: {e}")

    return False


def extract_imdb_id(text: str) -> Optional[str]:
    match = re.search(r"(tt\d{7,9})", text)
    return match.group(1) if match else None


def fetch_poster_url_and_store(imdb_id: str) -> Optional[str]:
    # Check if URL already exists in cache
    existing = get_entry(imdb_id)
    if existing and existing.get("poster_url"):
        print(f"[CACHE] Using cached poster URL for {imdb_id}")
        return existing["poster_url"]
    
    # Fetch fresh from IMDb
    url = fetch_poster_url(imdb_id)
    if url:
        update_entry(imdb_id, {"poster_url": url})
        print(f"[IMDB→CACHE] Scraped and cached new poster URL for {imdb_id}")
    else:
        print(f"[IMDB] No poster URL found on IMDb for {imdb_id}")
    return url


def download_poster_from_cache(imdb_id: str, save_path: Path) -> bool:
    entry = get_entry(imdb_id)
    if not entry or not entry.get("poster_url"):
        print(f"[CACHE] No poster_url cached for {imdb_id}")
        return False
    return download_image(entry["poster_url"], save_path)


def process_movie_files(video_files: List[Path]):
    """Fetch and store poster URL for each movie file."""
    for video in video_files:
        imdb_id = extract_imdb_id(video.stem)
        if not imdb_id:
            print(f"[SKIP] No IMDb ID in {video.name}")
            continue
        print(f"[PROCESS] Checking poster URL for movie {imdb_id}...")
        fetch_poster_url_and_store(imdb_id)


# def process_series_files(video_files: List[Path]):
#     """
#     Downloads posters/thumbnails for episodes with unique names, 
#     so they don't overwrite 'poster.jpg'.
#     Example filename: poster_tt1234567_s01e02.jpg
#     """
#     for video in video_files:
#         imdb_id = extract_imdb_id(video.stem)
#         if not imdb_id:
#             print(f"[SKIP] No IMDb ID in {video.name}")
#             continue

#         # Extract season and episode info from filename or folder structure
#         # Adjust your extraction logic here if needed
#         season, episode = None, None
#         season_match = re.search(r"[Ss](\d{1,2})", video.stem)
#         episode_match = re.search(r"[Ee](\d{1,2})", video.stem)
#         if season_match:
#             season = int(season_match.group(1))
#         if episode_match:
#             episode = int(episode_match.group(1))

#         dest_dir = video.parent

#         # Filename example: poster_tt1234567_s01e02.jpg
#         filename_parts = [f"poster_{imdb_id}"]
#         if season is not None:
#             filename_parts.append(f"s{season:02d}")
#         if episode is not None:
#             filename_parts.append(f"e{episode:02d}")
#         filename = "_".join(filename_parts) + ".jpg"
#         save_path = dest_dir / filename

#         if save_path.exists():
#             print(f"[SKIP] Thumbnail already exists: {save_path.name}")
#             continue

#         print(f"[SCRAPE] Fetching thumbnail for episode {imdb_id} S{season}E{episode}")
#         poster_url = fetch_poster_url(imdb_id)
#         if poster_url:
#             success = download_image(poster_url, save_path)
#             if not success:
#                 print(f"[FAIL] Couldn't save thumbnail for {imdb_id} S{season}E{episode}")
#         else:
#             print(f"[NOT FOUND] No thumbnail for {imdb_id} S{season}E{episode}")
def process_series_root_folders(series_dir: Path):
    """
    Looks for IMDb ID in the series folder name and downloads poster.jpg if not already present.
    """
    for folder in series_dir.iterdir():
        if not folder.is_dir():
            continue

        imdb_id = extract_imdb_id(folder.name)
        if not imdb_id:
            print(f"[SKIP] No IMDb ID in folder name: {folder.name}")
            continue

        poster_path = folder / "poster.jpg"
        if poster_path.exists():
            print(f"[SKIP] Series poster already exists: {poster_path}")
            continue

        print(f"[SCRAPE] Fetching series poster for {folder.name}")
        poster_url = fetch_poster_url(imdb_id)
        if poster_url:
            success = download_image(poster_url, poster_path)
            if not success:
                print(f"[FAIL] Couldn't save series poster for {imdb_id}")
        else:
            print(f"[NOT FOUND] No poster for series {imdb_id}")


def process_series_files(video_files: List[Path]):
    """
    Downloads thumbnails for episodes using:
    <original_episode_filename>-thumb.jpg
    """
    for video in video_files:
        imdb_id = extract_imdb_id(video.stem)
        if not imdb_id:
            print(f"[SKIP] No IMDb ID in {video.name}")
            continue

        dest_dir = video.parent
        thumb_name = f"{video.stem}-thumb.jpg"
        save_path = dest_dir / thumb_name

        if save_path.exists():
            print(f"[SKIP] Thumbnail already exists: {save_path.name}")
            continue

        print(f"[PROCESS] Checking thumbnail for {video.name}...")
        poster_url = fetch_poster_url_and_store(imdb_id)
        if poster_url:
            success = download_image(poster_url, save_path)
            if not success:
                print(f"[FAIL] Couldn't save thumbnail for {video.name}")
        else:
            print(f"[SKIP] No thumbnail URL available for {video.name}")


def process_episode_posters_from_metadata(metadata_path: Path):
    """
    For each episode in media_metadata.json with an empty poster_url, fetch and update the poster_url.
    """
    import json
    from core.media_metadata_cache import update_entry

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    updated = 0
    for imdb_id, entry in metadata.items():
        if entry.get("type") == "episode" and not entry.get("poster_url"):
            print(f"[EPISODE] Processing {imdb_id} ({entry.get('title', '')})") 
            url = fetch_poster_url_and_store(imdb_id)
            if url:
                updated += 1
def scrape_full_movie_metadata(imdb_id: str) -> dict:
    """
    Scrape title, year, summary, and poster_url from IMDb for a given movie IMDb ID.
    Updates the media_metadata cache and returns the entry dict.
    """
    url = f"https://www.imdb.com/title/{imdb_id}/"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"[{imdb_id}] Failed with status {response.status_code}")
            return {}
        soup = BeautifulSoup(response.text, "html.parser")
        # Title
        title_tag = soup.find("meta", property="og:title")
        # coerce meta attribute to string when present to avoid bs4 AttributeValueList typing
        title = str(title_tag.get("content")) if title_tag and title_tag.get("content") else ""
        # Clean title: remove ' - IMDb' and anything after ' ('
        if title:
            title = title.replace(" - IMDb", "").strip()
            if " (" in title:
                title = title.split(" (", 1)[0].strip()
        # Year
        year = ""
        year_tag = soup.find("span", id="titleYear")
        if year_tag is not None:
            a_tag = year_tag.find("a")
            if a_tag is not None and getattr(a_tag, 'text', None):
                try:
                    year = a_tag.text.strip()
                except Exception:
                    year = ""
        else:
            # Try to extract from title or elsewhere
            year_match = None
            title_tag_obj = getattr(soup, 'title', None)
            title_text = getattr(title_tag_obj, 'text', None) if title_tag_obj is not None else None
            if title_text:
                year_match = re.search(r"(19|20)\d{2}", title_text)
            if year_match:
                year = year_match.group(0)
        # Summary/Plot
        summary = ""
        plot_tag = soup.find("span", {"data-testid": "plot-l"})
        if not plot_tag:
            plot_tag = soup.find("span", {"data-testid": "plot-xl"})
        if not plot_tag:
            plot_tag = soup.find("div", class_="summary_text")
        if plot_tag:
            summary = plot_tag.text.strip()
        # Poster URL
        poster_url = fetch_poster_url(imdb_id)
        # Compose entry
        # If the media cache already has an episodes map for this IMDb ID, prefer preserving 'series' type
        try:
            existing = get_entry(imdb_id) or {}
        except Exception:
            existing = {}

        entry = {
            "title": title,
            "year": year,
            "summary": summary,
            "poster_url": poster_url or ""
        }
        # Only set type to 'movie' if there is no episodes map present
        if not existing.get('episodes'):
            entry['type'] = 'movie'
        else:
            # preserve existing type (likely 'series')
            entry['type'] = existing.get('type', 'movie')

        update_entry(imdb_id, entry)
        print(f"[SCRAPED] Metadata for {imdb_id} added to cache.")
        return entry
    except Exception as e:
        print(f"[{imdb_id}] Error scraping metadata: {e}")
        return {}


# def scrape_movie_posters():
#     process_movie_files(MOVIES_DIR)

# def scrape_series_thumbnails():
#     process_series_files(SERIES_DIR)
def scrape_movie_posters():
    movie_files = [p for p in MOVIES_DIR.rglob("*") if p.suffix.lower() in [".mkv", ".mp4", ".avi", ".mov"]]
    print(f"[INFO] Found {len(movie_files)} movie files.")
    process_movie_files(movie_files)

def scrape_series_thumbnails():
    series_files = [p for p in SERIES_DIR.rglob("*") if p.suffix.lower() in [".mkv", ".mp4", ".avi", ".mov"]]
    print(f"[INFO] Found {len(series_files)} series files.")
    process_series_files(series_files)

def scrape_series_root_folders():
    print("[INFO] Scanning for series poster folders...")
    process_series_root_folders(SERIES_DIR)



def main():
    print("[INFO] Scanning for movie files...")
    # movie_files = [p for p in MOVIES_DIR.rglob("*") if p.suffix.lower() in [".mkv", ".mp4", ".avi", ".mov"]]
    # print(f"[INFO] Found {len(movie_files)} movie files.")
    # process_movie_files(movie_files)

    # print("[INFO] Scanning for series files...")
    # series_files = [p for p in SERIES_DIR.rglob("*") if p.suffix.lower() in [".mkv", ".mp4", ".avi", ".mov"]]
    # print(f"[INFO] Found {len(series_files)} series files.")
    # process_series_files(series_files)
    # To update episode posters from metadata:
    metadata_path = Path(__file__).parent.parent / "cache" / "media_metadata.json"
    process_episode_posters_from_metadata(metadata_path)


if __name__ == "__main__":
    main()
