# gui/scrape_window.py
import tkinter as tk
from actions.custom_imdb_web_poster_scraper import (
    scrape_movie_posters, scrape_series_thumbnails, scrape_series_root_folders,
    process_episode_posters_from_metadata, download_image
)
from pathlib import Path
from config import MOVIES_DIR, SERIES_DIR
import json

class ScrapeWindow(tk.Frame):
    def __init__(self, master, on_back, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        label = tk.Label(self, text="Scrape Images", font=("Arial", 14))
        label.pack(pady=10)
        # btn_scrape = tk.Button(self, text="Scrape All Images", command=self.do_scrape)
        # btn_scrape.pack(pady=5)
        btn_update_main = tk.Button(self, text="Update Movie/Series Poster URLs", command=self.update_main_posters)
        btn_update_main.pack(pady=5)
        btn_update_episodes = tk.Button(self, text="Update Episode Thumbnails URLs", command=self.update_episode_thumbnails)
        btn_update_episodes.pack(pady=5)
        btn_download = tk.Button(self, text="Download Posters/Thumbnails", command=self.download_all_images)
        btn_download.pack(pady=5)
        btn_back = tk.Button(self, text="Back", command=on_back)
        btn_back.pack(pady=10)
        self.status = tk.Label(self, text="")
        self.status.pack(pady=5)

    def do_scrape(self):
        try:
            scrape_movie_posters()
            scrape_series_root_folders()
            scrape_series_thumbnails()
            self.status.config(text="Scraping complete.")
        except Exception as e:
            self.status.config(text=f"Error: {e}")

    def update_main_posters(self):
        try:
            scrape_movie_posters()
            scrape_series_root_folders()
            self.status.config(text="Updated movie/series poster URLs in cache.")
        except Exception as e:
            self.status.config(text=f"Error: {e}")

    def update_episode_thumbnails(self):
        try:
            metadata_path = Path(__file__).parent.parent / "cache" / "media_metadata.json"
            process_episode_posters_from_metadata(metadata_path)
            self.status.config(text="Updated episode thumbnail URLs in cache.")
        except Exception as e:
            self.status.config(text=f"Error: {e}")

    def download_all_images(self):
        try:
            metadata_path = Path(__file__).parent.parent / "cache" / "media_metadata.json"
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            count = 0
            for imdb_id, entry in metadata.items():
                url = entry.get("poster_url")
                if not url:
                    continue
                if entry.get("type") == "movie":
                    for p in MOVIES_DIR.rglob(f"*{imdb_id}*"):
                        if p.suffix.lower() in [".mkv", ".mp4", ".avi", ".mov"]:
                            poster_path = p.parent / "poster.jpg"
                            if download_image(url, poster_path):
                                count += 1
                elif entry.get("type") == "series":
                    for folder in SERIES_DIR.rglob(f"*{imdb_id}*"):
                        if folder.is_dir():
                            poster_path = folder / "poster.jpg"
                            if download_image(url, poster_path):
                                count += 1
                elif entry.get("type") == "episode":
                    for p in SERIES_DIR.rglob(f"*{imdb_id}*"):
                        if p.suffix.lower() in [".mkv", ".mp4", ".avi", ".mov"]:
                            thumb_path = p.parent / f"{p.stem}-thumb.jpg"
                            if download_image(url, thumb_path):
                                count += 1
            self.status.config(text=f"Downloaded {count} images from cache.")
        except Exception as e:
            self.status.config(text=f"Error: {e}")
