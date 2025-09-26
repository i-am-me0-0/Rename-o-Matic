# main.py (entry point only)

import sys
import os
if len(sys.argv) > 1 and sys.argv[1].lower() == "test":
    os.environ["RENAMER_CONFIG_FILE"] = "testconfig.ini"
from config import OMDB_API_KEY
from gui.app import launch_app

def main():
    if OMDB_API_KEY == "key" or not OMDB_API_KEY.strip():
        print("❌ OMDB API key is missing. Please add it to the config.ini under [General].")
        return
    launch_app()

if __name__ == "__main__":
    main()
