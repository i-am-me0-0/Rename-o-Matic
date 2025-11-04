#config.py
import configparser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import os
import sys


#CONFIG_FILE = Path("config.ini")
CONFIG_FILE = Path(os.environ.get("RENAMER_CONFIG_FILE", "config.ini"))

DEFAULTS = {
    "Paths": {
        "movies_dir": "./testLibrary/movies",
        "series_dir": "./testLibrary/series",
        "log_file": "rename_log.txt",
        "dry_run_log": "dry_run_log.txt",
        "planned_renames_file": "planned_renames.json"
    },
    "Extensions": {
        "video": ".mkv, .mp4, .avi",
        "subtitle": ".srt"
    },
    "Series": {
        "edge_keywords": ""#"animated movie cut"
        
    },
    "SeriesAliases": {
        "alias-1": "Alias 1",
        "alias-2": "Alias 2"
    },
    "General": {
        "lang_codes": ", ".join(["", "en", "de", "fr", "es", "nl"]),
        "movie_folder_location": "root",  # or "source"
        "default_include": "1",           # or "0"
        "create_movie_subfolders": "False",  # or False
        "log_level": "info",  # or "debug", "warning", "error", "critical"
        "prepend_episode_title_to_extras": "True",  # or False
        "ui_debug": "False"
    },
    "OMDb": {
        "omdb_api_key": "key",
        "omdb_base_url": "http://www.omdbapi.com/",
        "omdb_request_delay": "0.2",
        "omdb_search_limit": "5",
        "user_agents": '"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36, Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/113.0.0.0 Safari/537.36"'
    },
    "PosterScraper": {
        "scrape_movie_posters": "true",
        "scrape_series_thumbnails": "true",
        "scrape_series_root_folders": "true"
    }
}

def strip_inline_comments(line):
    in_quotes = False
    result = ''
    for i, c in enumerate(line):
        if c in ('"', "'"):
            in_quotes = not in_quotes
        if c == '#' and not in_quotes:
            break
        result += c
    return result.rstrip()

def read_config_without_inline_comments(path):
    lines = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            # Remove inline comments unless inside quotes
            lines.append(strip_inline_comments(line))
    return '\n'.join(lines)

def init_config():
    config = configparser.ConfigParser()
    if not CONFIG_FILE.exists():
        for section, opts in DEFAULTS.items():
            config[section] = opts
        with open(CONFIG_FILE, "w", encoding="utf-8") as cfg:
            cfg.write("# Configuration file for renamer\n")
            cfg.write("# create_folders: whether to create destination folders\n")
            cfg.write("# perform_rename: whether to actually rename/move files\n")
            cfg.write("# omdb_api_key: replace with your key\n\n")
            config.write(cfg)
        print(f"[config] Created default configuration at {CONFIG_FILE}")
    # Read config with inline comments stripped
    config.read_string(read_config_without_inline_comments(CONFIG_FILE))
    return config

cfg = init_config()



MOVIES_DIR = Path(cfg["Paths"]["movies_dir"])
SERIES_DIR = Path(cfg["Paths"]["series_dir"])
LOG_FILE = Path(cfg["Paths"]["log_file"])
#DRY_RUN_LOG_FILE = Path(cfg["Paths"]["dry_run_log"])


VIDEO_EXTENSIONS = [ext.strip() for ext in cfg["Extensions"]["video"].split(",")]
SUBTITLE_EXTENSIONS = [ext.strip() for ext in cfg["Extensions"]["subtitle"].split(",")]

EDGE_CASE_KEYWORDS = [kw.strip() for kw in cfg["Series"]["edge_keywords"].split(",")]
SERIES_ALIASES = {
    k.strip(): v.strip()
    for k, v in cfg["SeriesAliases"].items()
} if "SeriesAliases" in cfg else {}


LANG_CODES = [lc.strip() for lc in cfg["General"]["lang_codes"].split(",")]
#second arg is default, example movie_folder_location = default root
MOVIE_FOLDER_LOCATION = cfg["General"].get("movie_folder_location", "root").strip().lower()
DEFAULT_INCLUDE = cfg["General"].get("default_include", "1").strip()
PREPEND_EPISODE_TITLE_TO_EXTRAS = cfg["General"].get("prepend_episode_title_to_extras", "True").strip().lower()

# OMDb API config
OMDB_API_KEY = cfg["OMDb"].get("omdb_api_key", "key").strip()
OMDB_BASE_URL = cfg["OMDb"].get("omdb_base_url", "http://www.omdbapi.com/").strip()
OMDB_REQUEST_DELAY = float(cfg["OMDb"].get("omdb_request_delay", "0.2"))
OMDB_SEARCH_LIMIT = int(cfg["OMDb"].get("omdb_search_limit", "5"))
USER_AGENTS = [ua.strip().strip('"') for ua in cfg["OMDb"].get("user_agents", "").split(",") if ua.strip()]
# CREATE_MOVIE_SUBFOLDERS = cfg["General"].get("create_movie_subfolders", "").strip()
CREATE_MOVIE_SUBFOLDERS = cfg["General"].get("create_movie_subfolders", "True").strip().lower() == "true"

# Poster scraper options
SCRAPE_MOVIE_POSTERS = cfg["PosterScraper"].get("scrape_movie_posters", "true").strip().lower() == "true"
SCRAPE_SERIES_THUMBNAILS = cfg["PosterScraper"].get("scrape_series_thumbnails", "true").strip().lower() == "true"
SCRAPE_SERIES_ROOT_FOLDERS = cfg["PosterScraper"].get("scrape_series_root_folders", "true").strip().lower() == "true"

# Preview file
#PREVIEW_FILE = Path(cfg["Paths"].get("preview_file", "planned_renames.txt"))

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

# Manual episode cache file
MANUAL_EPISODE_CACHE_FILE = CACHE_DIR / cfg["Paths"].get("manual_episode_cache_file", "manual_episode_cache.json")

# Manual episode title cache file (for manual episode title→id mapping)
MANUAL_EPISODE_TITLE_CACHE_FILE = CACHE_DIR / cfg["Paths"].get("manual_episode_title_cache_file", "manual_episode_title_cache.json")

# IMDb cache file
IMDB_CACHE_FILE = CACHE_DIR / cfg["Paths"].get("imdb_cache_file", "imdb_cache.json")
PLANNED_RENAMES_FILE = Path(cfg["Paths"].get("planned_renames_file", "planned_renames.json"))

LOG_LEVEL = cfg["General"].get("log_level", "info").strip().lower()
# SKIP_IMDB_IDS = cfg["General"].get("skip_imdb_ids", fallback='').split(',')
# Convert to set for O(1) lookup performance
SKIP_IMDB_IDS = {id.strip() for id in cfg["General"].get("skip_imdb_ids", "").split(",") if id.strip()}

MEDIA_METADATA_FILE = CACHE_DIR / "media_metadata.json"
if not MEDIA_METADATA_FILE.exists():
    MEDIA_METADATA_FILE.write_text("{}", encoding="utf-8")

def debug_print(*args, **kwargs):
    if LOG_LEVEL == "debug":
        print(*args, **kwargs)


# UI-level temporary diagnostics (separate from LOG_LEVEL)
# Enable by setting 'ui_debug' = true in the [General] section of config.ini
UI_DEBUG = cfg["General"].get("ui_debug", "false").strip().lower() == "true"

def ui_debug_print(*args, **kwargs):
    if UI_DEBUG:
        print(*args, **kwargs)




def reload_config():
    pass
#     global cfg
#     cfg = configparser.ConfigParser()
#     cfg.read_string(read_config_without_inline_comments(CONFIG_FILE))
#     reload_globals()  # update globals accordingly
#     # You may want to also update other global vars here if used externally

# # expose reload function


