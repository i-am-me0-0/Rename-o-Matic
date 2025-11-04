import os
import sys
import csv
import gzip
import sqlite3
import subprocess
import importlib
import requests
from fastapi import FastAPI, Query
import uvicorn
from typing import Optional
from bs4 import BeautifulSoup

# ---- Auto-install dependencies ----
def ensure_dependencies():
    pkgs = ["fastapi", "uvicorn", "requests"]
    for pkg in pkgs:
        try:
            importlib.import_module(pkg)
        except ImportError:
            print(f"Installing missing dependency: {pkg}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

ensure_dependencies()

# ---- Config ----
DATASETS = {
    "title.basics.tsv.gz": "https://datasets.imdbws.com/title.basics.tsv.gz",
    "title.episode.tsv.gz": "https://datasets.imdbws.com/title.episode.tsv.gz",
}

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
BASICS_FILE = os.path.join(DATA_DIR, "title.basics.tsv.gz")
EPISODES_FILE = os.path.join(DATA_DIR, "title.episode.tsv.gz")
DB_PATH = os.path.join(DATA_DIR, "imdb.db")

app = FastAPI(title="Local IMDB API (SQLite Offline OMDb Fallback)")

# ---- Download if missing ----
def download_if_missing():
    for fname, url in DATASETS.items():
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath):
            print(f"Downloading {fname} ...")
            resp = requests.get(url, stream=True)
            resp.raise_for_status()
            with open(fpath, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            print(f"Saved {fname} ({os.path.getsize(fpath)/1e6:.2f} MB)")
        else:
            print(f"Found {fname}")

# ---- Build database ----
def build_database():
    if os.path.exists(DB_PATH):
        print("Database already exists, skipping build.")
        return

    print("Building imdb.db ... this will take a few minutes.")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE basics (
            tconst TEXT PRIMARY KEY,
            titleType TEXT,
            primaryTitle TEXT,
            originalTitle TEXT,
            isAdult INTEGER,
            startYear TEXT,
            endYear TEXT,
            runtimeMinutes TEXT,
            genres TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE episodes (
            tconst TEXT PRIMARY KEY,
            parentTconst TEXT,
            seasonNumber TEXT,
            episodeNumber TEXT
        )
    """)

    # Load basics
    with gzip.open(BASICS_FILE, mode="rt", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        batch = []
        ALLOWED_TYPES = {"movie", "tvSeries", "tvMiniSeries", "tvEpisode"}
        for i, row in enumerate(reader, start=1):
            if row.get("titleType") not in ALLOWED_TYPES:
                continue
            batch.append((
                row.get("tconst"),
                row.get("titleType"),
                row.get("primaryTitle"),
                row.get("originalTitle"),
                row.get("isAdult"),
                row.get("startYear"),
                row.get("endYear"),
                row.get("runtimeMinutes"),
                row.get("genres"),
            ))
            if len(batch) >= 50000:
                cur.executemany("INSERT OR REPLACE INTO basics VALUES (?,?,?,?,?,?,?, ?,?)", batch)
                conn.commit()
                batch.clear()
                print(f"Inserted {i:,} titles...")
        if batch:
            cur.executemany("INSERT OR REPLACE INTO basics VALUES (?,?,?,?,?,?,?, ?,?)", batch)
            conn.commit()

    # Load episodes
    if os.path.exists(EPISODES_FILE):
        with gzip.open(EPISODES_FILE, mode="rt", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            batch = []
            for i, row in enumerate(reader, start=1):
                batch.append((
                    row.get("tconst"),
                    row.get("parentTconst"),
                    row.get("seasonNumber"),
                    row.get("episodeNumber"),
                ))
                if len(batch) >= 50000:
                    cur.executemany("INSERT OR REPLACE INTO episodes VALUES (?,?,?,?)", batch)
                    conn.commit()
                    batch.clear()
                    print(f"Inserted {i:,} episodes...")
            if batch:
                cur.executemany("INSERT OR REPLACE INTO episodes VALUES (?,?,?,?)", batch)
                conn.commit()

    conn.execute("CREATE INDEX IF NOT EXISTS idx_title ON basics(primaryTitle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON basics(titleType)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_episode_parent ON episodes(parentTconst)")
    conn.commit()
    conn.close()
    print("Database build complete.")

import argparse
import time

# ---- Utility for file update check ----
def download_if_newer(fname, url):
    """Downloads the file only if modified on server"""
    fpath = os.path.join(DATA_DIR, fname)
    headers = {}
    if os.path.exists(fpath):
        headers['If-Modified-Since'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT',
                                                     time.gmtime(os.path.getmtime(fpath)))
    resp = requests.get(url, stream=True, headers=headers)
    if resp.status_code == 304:
        print(f"{fname} is up-to-date.")
        return False
    resp.raise_for_status()
    with open(fpath, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    print(f"Downloaded updated {fname} ({os.path.getsize(fpath)/1e6:.2f} MB)")
    return True

def update_database():
    """Incremental update of imdb.db"""
    print("Checking for dataset updates...")
    updated_basics = download_if_newer("title.basics.tsv.gz", DATASETS["title.basics.tsv.gz"])
    updated_episodes = download_if_newer("title.episode.tsv.gz", DATASETS["title.episode.tsv.gz"])
    
    if not updated_basics and not updated_episodes:
        print("No updates found. Exiting update mode.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Only update basics if new
    if updated_basics:
        print("Updating basics table...")
        with gzip.open(BASICS_FILE, mode="rt", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            ALLOWED_TYPES = {"movie", "tvSeries", "tvMiniSeries", "tvEpisode"}
            batch = []
            for row in reader:
                if row.get("titleType") not in ALLOWED_TYPES:
                    continue
                batch.append((
                    row.get("tconst"),
                    row.get("titleType"),
                    row.get("primaryTitle"),
                    row.get("originalTitle"),
                    row.get("isAdult"),
                    row.get("startYear"),
                    row.get("endYear"),
                    row.get("runtimeMinutes"),
                    row.get("genres"),
                ))
                if len(batch) >= 50000:
                    cur.executemany("INSERT OR REPLACE INTO basics VALUES (?,?,?,?,?,?,?,?,?)", batch)
                    conn.commit()
                    batch.clear()
            if batch:
                cur.executemany("INSERT OR REPLACE INTO basics VALUES (?,?,?,?,?,?,?,?,?)", batch)
                conn.commit()
        print("Basics table updated.")

    # Only update episodes if new
    if updated_episodes:
        print("Updating episodes table...")
        with gzip.open(EPISODES_FILE, mode="rt", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            batch = []
            for row in reader:
                batch.append((
                    row.get("tconst"),
                    row.get("parentTconst"),
                    row.get("seasonNumber"),
                    row.get("episodeNumber"),
                ))
                if len(batch) >= 50000:
                    cur.executemany("INSERT OR REPLACE INTO episodes VALUES (?,?,?,?)", batch)
                    conn.commit()
                    batch.clear()
            if batch:
                cur.executemany("INSERT OR REPLACE INTO episodes VALUES (?,?,?,?)", batch)
                conn.commit()
        print("Episodes table updated.")

    conn.close()
    print("Incremental update complete.")



# ---- Poster table ----
def ensure_poster_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posters (
            imdbID TEXT PRIMARY KEY,
            posterURL TEXT
        )
    """)
    conn.commit()
    conn.close()

# ---- Dynamic fetchers ----
def fetch_imdb_poster(imdbID):
    """Scrapes IMDb page for the og:image poster URL"""
    url = f"https://www.imdb.com/title/{imdbID}/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        meta = soup.find("meta", property="og:image")
        if meta:
            return meta.get("content")
    except Exception as e:
        print(f"[IMDb poster fetch failed] {imdbID}: {e}")
    return None

def fetch_wikipedia_poster(title):
    """Fetch poster URL from Wikipedia page image thumbnail"""
    try:
        api_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": title,
            "prop": "pageimages",
            "format": "json",
            "pithumbsize": 500
        }
        r = requests.get(api_url, params=params, timeout=5)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            if thumb.get("source"):
                return thumb["source"]
    except Exception as e:
        print(f"[Wikipedia poster fetch failed] {title}: {e}")
    return None

def get_poster(imdbID, title=None):
    """Returns poster URL from DB or fetches dynamically"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT posterURL FROM posters WHERE imdbID=?", (imdbID,))
    row = cur.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]

    # Try IMDb first
    poster = fetch_imdb_poster(imdbID)
    if not poster and title:
        poster = fetch_wikipedia_poster(title)

    if poster:
        cur.execute("INSERT OR REPLACE INTO posters (imdbID, posterURL) VALUES (?,?)", (imdbID, poster))
        conn.commit()
    conn.close()
    return poster

# ---- Update make_response ----
def make_response(row, ep=None):
    imdbID = row[0]
    title = row[2]
    poster = get_poster(imdbID, title)
    resp = {
        "imdbID": imdbID,
        "Title": title,
        "Type": row[1],
        "Year": row[5],
        "Runtime": row[7],
        "Genre": row[8],
        "Poster": poster or None,
        "Response": "True",
    }
    if ep:
        resp.update({
            "Season": ep[2],
            "Episode": ep[3],
            "SeriesID": ep[1],
        })
    return resp

# ---- Query helpers ----
def get_db():
    return sqlite3.connect(DB_PATH)

# def make_response(row, ep=None):
#     resp = {
#         "imdbID": row[0],
#         "Title": row[2],
#         "Type": row[1],
#         "Year": row[5],
#         "Runtime": row[7],
#         "Genre": row[8],
#         "Response": "True",
#     }
#     if ep:
#         resp.update({
#             "Season": ep[2],
#             "Episode": ep[3],
#             "SeriesID": ep[1],
#         })
#     return resp

# ---- API endpoints ----
@app.get("/")
def get_item(
    i: Optional[str] = Query(None, description="IMDB ID (e.g. tt1234567)"),
    t: Optional[str] = Query(None, description="Exact title"),
    s: Optional[str] = Query(None, description="Search substring"),
    type: Optional[str] = Query(None, description="Filter type"),
    max: int = Query(10, description="Max search results"),
):
    if not any([i, t, s]):
        return {"Response": "False", "Error": "Specify ?i=, ?t=, or ?s="}

    conn = get_db()
    cur = conn.cursor()

    if i:
        cur.execute("SELECT * FROM basics WHERE tconst=?", (i,))
        row = cur.fetchone()
        if not row:
            return {"Response": "False", "Error": "Not found"}
        cur.execute("SELECT * FROM episodes WHERE tconst=?", (i,))
        ep = cur.fetchone()
        conn.close()
        return make_response(row, ep)

    if t:
        q = "SELECT * FROM basics WHERE lower(primaryTitle)=?"
        params = (t.lower(),)
        if type:
            q += " AND titleType=?"
            params += (type,)
        cur.execute(q, params)
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"Response": "False", "Error": "Title not found"}
        return make_response(row)

    # if s:
    #     q = "SELECT tconst, titleType, primaryTitle, startYear FROM basics WHERE lower(primaryTitle) LIKE ?"
    #     params = (f"%{s.lower()}%",)
    #     if type:
    #         q += " AND titleType=?"
    #         params += (type,)
    #     q += " LIMIT ?"
    #     params += (max,)
    #     cur.execute(q, params)
    #     results = [
    #         {"imdbID": r[0], "Type": r[1], "Title": r[2], "Year": r[3]} for r in cur.fetchall()
    #     ]
    #     conn.close()
    #     return {
    #         "Search": results,
    #         "totalResults": len(results),
    #         "Response": "True" if results else "False",
    #     }

    if s:
        s_lower = s.lower()
        results = []

        # Exact title matches first
        cur.execute("""
            SELECT tconst, titleType, primaryTitle, startYear
            FROM basics
            WHERE lower(primaryTitle)=?
            ORDER BY CASE titleType
                WHEN 'movie' THEN 1
                WHEN 'tvSeries' THEN 2
                WHEN 'tvMiniSeries' THEN 3
                WHEN 'tvEpisode' THEN 4 ELSE 5 END,
                CAST(startYear AS INTEGER) ASC
        """, (s_lower,))
        for r in cur.fetchall():
            results.append({"Title": r[2], "Year": r[3], "imdbID": r[0], "Type": r[1]})

        # Partial matches (excluding exact title)
        cur.execute(f"""
            SELECT tconst, titleType, primaryTitle, startYear
            FROM basics
            WHERE lower(primaryTitle) LIKE ?
            AND lower(primaryTitle)<>?
            ORDER BY CASE titleType
                WHEN 'movie' THEN 1
                WHEN 'tvSeries' THEN 2
                WHEN 'tvMiniSeries' THEN 3
                WHEN 'tvEpisode' THEN 4 ELSE 5 END,
                CAST(startYear AS INTEGER) ASC
            LIMIT ?
        """, (f"%{s_lower}%", s_lower, max))
        for r in cur.fetchall():
            results.append({"Title": r[2], "Year": r[3], "imdbID": r[0], "Type": r[1]})

        conn.close()
        return {
            "Search": results[:max],
            "totalResults": len(results),
            "Response": "True" if results else "False",
        }



    conn.close()
    return {"Response": "False", "Error": "Unhandled query"}

# ---- Entry ----
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="Incrementally update IMDb database")
    args = parser.parse_args()

    print("=== Local IMDb SQLite API ===")
    download_if_missing()

    if not os.path.exists(DB_PATH):
        build_database()
    elif args.update:
        update_database()

    

    # ---- Poster table ----
    ensure_poster_table()
        

    print("Server running on http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)

