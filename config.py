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
    # ============================================================================
    # [Essential Settings] - Edit these regularly
    # ============================================================================
    
    "Paths": {
        # Your media library locations
        "movies_dir": "./testLibrary/movies",
        "series_dir": "./testLibrary/series"
    },
    
    "OMDb": {
        # Your OMDb API key (get one at http://www.omdbapi.com/apikey.aspx)
        "omdb_api_key": "key"
    },
    
    "SeriesAliases": {
        # Map non-standard folder names to proper series names
        # Format: folder_name = Canonical Series Name
        #"alias-1": "Alias 1",
        #"alias-2": "Alias 2"
    },
    
    # ============================================================================
    # [General Settings] - Occasionally adjusted
    # ============================================================================
    
    "General": {
        # Subtitle language codes (comma-separated, blank = no language tag)
        "lang_codes": ", ".join(["", "en", "de", "fr", "es", "nl"]),
        
        # Where to create movie folders: 'root' (in movies_dir) or 'source' (keep in original subfolder)
        "movie_folder_location": "root",
        
        # Whether to create subfolders for each movie (true/false)
        "create_movie_subfolders": "False",
        
        # New entries in preview are checked by default (1) or unchecked (0)
        "default_include": "1",
        
        # Include episode title in extras tag (true/false)
        "prepend_episode_title_to_extras": "True",
        
        # Console debug output (true/false) - shows internal processing details
        "debug_mode": "False",
        
        # UI debug output (true/false) - shows detailed GUI diagnostics
        "ui_debug": "False",
        
        # Skip these IMDb IDs during processing (comma-separated)
        "skip_imdb_ids": ""
    },
    
    "Extensions": {
        # Recognized file extensions (comma-separated)
        "video": ".mkv, .mp4, .avi",
        "subtitle": ".srt"
    },
    
    "Series": {
        # Keywords that indicate special/edge-case episodes (comma-separated)
        "edge_keywords": ""
    },
    
    # ============================================================================
    # [Advanced Settings] - Rarely need changes
    # ============================================================================
    
    "OMDbAdvanced": {
        # OMDb API endpoint (change for testing with local stub)
        "omdb_base_url": "http://www.omdbapi.com/",
        
        # Delay between OMDb API requests (seconds)
        "omdb_request_delay": "0.2",
        
        # Maximum search results to consider
        "omdb_search_limit": "5",
        
        # User agent strings for web scraping (comma-separated, use double quotes)
        "user_agents": '"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36, Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/113.0.0.0 Safari/537.36"'
    },
    
    "InternalPaths": {
        # Cache and log file names (change only if you know what you're doing)
        "log_file": "rename_log.txt",
        "episode_cache_file": "episode_cache.json",
        "manual_episode_cache_file": "manual_episode_cache.json",
        "manual_episode_title_cache_file": "manual_episode_title_cache.json",
        "imdb_cache_file": "imdb_cache.json",
        "planned_renames_file": "planned_renames.json"
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
            cfg.write("# Media Renamer Configuration\n")
            cfg.write("# Essential settings at top, advanced settings at bottom\n\n")
            config.write(cfg)
        print(f"[config] Created default configuration at {CONFIG_FILE}")
    # Read config with inline comments stripped
    config.read_string(read_config_without_inline_comments(CONFIG_FILE))
    return config

cfg = init_config()



MOVIES_DIR = Path(cfg["Paths"]["movies_dir"])
SERIES_DIR = Path(cfg["Paths"]["series_dir"])
LOG_FILE = Path(cfg["InternalPaths"]["log_file"])


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
OMDB_API_KEY = cfg["OMDb"]["omdb_api_key"].strip()
OMDB_BASE_URL = cfg["OMDbAdvanced"]["omdb_base_url"].strip()
OMDB_REQUEST_DELAY = float(cfg["OMDbAdvanced"]["omdb_request_delay"])
OMDB_SEARCH_LIMIT = int(cfg["OMDbAdvanced"]["omdb_search_limit"])
USER_AGENTS = [ua.strip().strip('"') for ua in cfg["OMDbAdvanced"]["user_agents"].split(",") if ua.strip()]
# CREATE_MOVIE_SUBFOLDERS = cfg["General"].get("create_movie_subfolders", "").strip()
CREATE_MOVIE_SUBFOLDERS = cfg["General"].get("create_movie_subfolders", "False").strip().lower() == "true"

# Poster scraper options
# SCRAPE_MOVIE_POSTERS = cfg["PosterScraper"].get("scrape_movie_posters", "true").strip().lower() == "true"
# SCRAPE_SERIES_THUMBNAILS = cfg["PosterScraper"].get("scrape_series_thumbnails", "true").strip().lower() == "true"
# SCRAPE_SERIES_ROOT_FOLDERS = cfg["PosterScraper"].get("scrape_series_root_folders", "true").strip().lower() == "true"

# Preview file
#PREVIEW_FILE = Path(cfg["Paths"].get("preview_file", "planned_renames.txt"))

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

# Cache and log file paths
MANUAL_EPISODE_CACHE_FILE = CACHE_DIR / cfg["InternalPaths"]["manual_episode_cache_file"]
MANUAL_EPISODE_TITLE_CACHE_FILE = CACHE_DIR / cfg["InternalPaths"]["manual_episode_title_cache_file"]
IMDB_CACHE_FILE = CACHE_DIR / cfg["InternalPaths"]["imdb_cache_file"]
PLANNED_RENAMES_FILE = Path(cfg["InternalPaths"]["planned_renames_file"])

DEBUG_MODE = cfg["General"].get("debug_mode", "false").strip().lower() == "true"
SKIP_IMDB_IDS = {id.strip() for id in cfg["General"].get("skip_imdb_ids", "").split(",") if id.strip()}

MEDIA_METADATA_FILE = CACHE_DIR / "media_metadata.json"
if not MEDIA_METADATA_FILE.exists():
    MEDIA_METADATA_FILE.write_text("{}", encoding="utf-8")

def debug_print(*args, **kwargs):
    if DEBUG_MODE:
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


