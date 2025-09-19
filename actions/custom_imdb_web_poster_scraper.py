# import time
# import random
# import requests
# from bs4 import BeautifulSoup
# from typing import List, Dict, Optional
# import os

# # User-Agent pool to rotate
# USER_AGENTS = [
#     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36",
#     "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/113.0.0.0 Safari/537.36",
#     "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/112.0.0.0 Safari/537.36",
#     "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
#     "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
# ]

# BASE_URL = "https://www.imdb.com/title/{imdb_id}/"
# session = requests.Session()

# # Get absolute path to the directory where this script is located
# SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# POSTER_DIR = os.path.join(SCRIPT_DIR, "posters")

# # Create poster directory if it doesn't exist
# os.makedirs(POSTER_DIR, exist_ok=True)


# def fetch_poster_url(imdb_id: str) -> Optional[str]:
#     url = BASE_URL.format(imdb_id=imdb_id)
#     headers = {
#         "User-Agent": random.choice(USER_AGENTS),
#         "Accept-Language": "en-US,en;q=0.9"
#     }

#     try:
#         response = session.get(url, headers=headers, timeout=10)
#         if response.status_code != 200:
#             print(f"[{imdb_id}] Failed with status {response.status_code}")
#             return None

#         soup = BeautifulSoup(response.text, "html.parser")

#         # Method 1: Look for poster in meta property og:image
#         meta = soup.find("meta", property="og:image")
#         if meta and meta.get("content"): # type: ignore
#             return meta["content"] # type: ignore

#         # Method 2 (fallback): Look for <img> inside a poster container
#         img = soup.select_one(".ipc-media img")
#         if img and img.get("src"):
#             return img["src"] # type: ignore

#     except Exception as e:
#         print(f"[{imdb_id}] Error: {e}")

#     return None


# def download_poster(imdb_id: str, poster_url: str, save_dir: str = POSTER_DIR) -> Optional[str]:
#     ext = os.path.splitext(poster_url)[-1].split("?")[0] or ".jpg"
#     filename = f"{imdb_id}{ext}"
#     filepath = os.path.join(save_dir, filename)

#     if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
#         print(f"📁 Poster already exists: {filename}")
#         return filepath

#     try:
#         response = requests.get(poster_url, stream=True, timeout=10)
#         if response.status_code == 200:
#             with open(filepath, "wb") as f:
#                 for chunk in response.iter_content(1024):
#                     f.write(chunk)
#             print(f"💾 Poster saved as {filename}")
#             return filepath
#         else:
#             print(f"[{imdb_id}] Failed to download poster. HTTP {response.status_code}")
#     except Exception as e:
#         print(f"[{imdb_id}] Error downloading poster: {e}")

#     return None


# # def scrape_posters(imdb_ids: List[str], delay: float = 2.0) -> Dict[str, Optional[str]]:
# #     posters = {}
# #     for imdb_id in imdb_ids:
# #         filename = f"{imdb_id}.jpg"
# #         filepath = os.path.join(POSTER_DIR, filename)

# #         if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
# #             print(f"📁 Already downloaded: {filename}")
# #             posters[imdb_id] = filepath
# #             continue

# #         print(f"🎬 Fetching: {imdb_id}")
# #         poster_url = fetch_poster_url(imdb_id)
# #         if poster_url:
# #             print(f"✅ Found poster: {poster_url}")
# #             download_poster(imdb_id, poster_url)
# #         else:
# #             print("❌ No poster found.")
# #         posters[imdb_id] = poster_url
# #         time.sleep(delay + random.uniform(0.2, 1.0))  # Randomized delay to avoid blocking
# #     return posters


# # # def main():
# # #     imdb_ids = [
# # #         "tt1213404",  # Legend of the Seeker
# # #         "tt0133093",  # The Matrix
# # #         "tt0903747",  # Breaking Bad
# # #         "tt3566834",
# # #         "tt0910970",
# # #         "tt0315327",
# # #         "tt0119654",
# # #         "tt0120912",
# # #         "tt1409024",
# # #         "tt1236283",
# # #         "tt1236288",
# # #         "tt1114258",
# # #         "tt10695770",  # Meta Runner
# # #         "tt13134916",
# # #         "tt10696624",
# # #         "tt10756490",
# # #         "tt13292040",
# # #         "tt13327702",
# # #         "tt21243388",
# # #         "tt21405118",
# # #     ]
# # #     posters = scrape_posters(imdb_ids)
# # #     print("\n🎞 Final poster file paths or URLs:")
# # #     for imdb_id, path in posters.items():
# # #          print(f"{imdb_id}: {path}")


# # if __name__ == "__main__":
# #     # main()
# #     # This only runs when called directly
# #     test_ids = ["tt0133093", "tt0903747"]
# #     scrape_posters(test_ids)

# #for debugging this file itself
# import sys
# from pathlib import Path

# # Add parent directory to sys.path
# sys.path.append(str(Path(__file__).resolve().parent.parent))




# # fetch_posters.py
# import re
# from pathlib import Path
# from typing import Optional
# from config import MOVIES_DIR, SERIES_DIR
# from core.file_utils import is_video_file
# from core.info_extractors import extract_movie_info, extract_episode_info
# # from custom_poster_scraper import fetch_poster_url, download_poster  # your scraper

# def get_all_video_files(root_dir: Path):
#     return [p for p in root_dir.rglob("*") if is_video_file(p)]

# def extract_imdb_id(text: str) -> Optional[str]:
#     match = re.search(r"(tt\d{7,9})", text)
#     return match.group(1) if match else None

# def process_video_files(video_files):
#     for video in video_files:
#         imdb_id = extract_imdb_id(video.stem)
#         if not imdb_id:
#             print(f"[SKIP] No IMDb ID found in: {video.name}")
#             continue

#         dest_dir = video.parent
#         poster_path = dest_dir / "poster.jpg"
#         if poster_path.exists():
#             print(f"[SKIP] Poster already exists: {poster_path}")
#             continue

#         print(f"[SCRAPE] Looking for poster for {imdb_id}")
#         poster_url = fetch_poster_url(imdb_id)
#         if poster_url:
#             success_path = download_poster(imdb_id, poster_url, save_dir=dest_dir)
#             if success_path:
#                 poster_path.rename(dest_dir / "poster.jpg")  # Rename to match expected name
#                 print(f"[SAVED] Poster saved: {poster_path}")
#             else:
#                 print(f"[FAIL] Couldn't save poster for {imdb_id}")
#         else:
#             print(f"[NOT FOUND] No poster for {imdb_id}")

# def main():
#     print("[INFO] Scanning for movie files...")
#     movie_files = get_all_video_files(MOVIES_DIR)
#     print(f"[INFO] Found {len(movie_files)} movie files.")
#     process_video_files(movie_files)

#     print("[INFO] Scanning for series files...")
#     series_files = get_all_video_files(SERIES_DIR)
#     print(f"[INFO] Found {len(series_files)} series files.")
#     process_video_files(series_files)

# if __name__ == "__main__":
#     main()

#custom_imdb_web_poster_scraper.py
import time
import random
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
import os
import re
from pathlib import Path
from config import MOVIES_DIR, SERIES_DIR, USER_AGENTS, SCRAPE_MOVIE_POSTERS, SCRAPE_SERIES_THUMBNAILS, SCRAPE_SERIES_ROOT_FOLDERS
from core.media_metadata_cache import update_entry, get_entry

BASE_URL = "https://www.imdb.com/title/{imdb_id}/"
session = requests.Session()


def fetch_poster_url(imdb_id: str) -> Optional[str]:
    url = BASE_URL.format(imdb_id=imdb_id)
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"[{imdb_id}] Failed with status {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        meta = soup.find("meta", property="og:image")
        if meta and meta.get("content"):
            return meta["content"]

        img = soup.select_one(".ipc-media img")
        if img and img.get("src"):
            return img["src"]

    except Exception as e:
        print(f"[{imdb_id}] Error: {e}")

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
    url = fetch_poster_url(imdb_id)
    if url:
        # Always overwrite poster_url with the custom-scraped value
        update_entry(imdb_id, {"poster_url": url})
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
        print(f"[SCRAPE] Fetching poster URL for movie {imdb_id}")
        url = fetch_poster_url_and_store(imdb_id)
        if url:
            print(f"[CACHED] Poster URL for {imdb_id}: {url}")
        else:
            print(f"[NOT FOUND] No poster for {imdb_id}")


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

        print(f"[SCRAPE] Fetching thumbnail for {video.name}")
        poster_url = fetch_poster_url(imdb_id)
        if poster_url:
            success = download_image(poster_url, save_path)
            if not success:
                print(f"[FAIL] Couldn't save thumbnail for {video.name}")
        else:
            print(f"[NOT FOUND] No thumbnail for {video.name}")


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
            print(f"[EPISODE] Fetching poster for {imdb_id} ({entry.get('title', '')})")
            url = fetch_poster_url(imdb_id)
            if url:
                update_entry(imdb_id, {"poster_url": url})
                print(f"[UPDATED] {imdb_id} poster_url set.")
                updated += 1
            else:
                print(f"[NOT FOUND] No poster for {imdb_id}")
    print(f"[DONE] Updated {updated} episode poster URLs.")


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
        title = title_tag["content"] if title_tag and title_tag.get("content") else ""
        # Clean title: remove ' - IMDb' and anything after ' ('
        if title:
            title = title.replace(" - IMDb", "").strip()
            if " (" in title:
                title = title.split(" (", 1)[0].strip()
        # Year
        year = ""
        year_tag = soup.find("span", id="titleYear")
        if year_tag and year_tag.find("a"):
            year = year_tag.find("a").text.strip()
        else:
            # Try to extract from title or elsewhere
            year_match = soup.title and re.search(r"(19|20)\d{2}", soup.title.text)
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
        entry = {
            "title": title,
            "year": year,
            "type": "movie",
            "summary": summary,
            "poster_url": poster_url or ""
        }
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
