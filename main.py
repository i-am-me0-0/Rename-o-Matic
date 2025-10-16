# main.py (entry point only)

import sys
import os
if len(sys.argv) > 1 and sys.argv[1].lower() == "test":
    os.environ["RENAMER_CONFIG_FILE"] = "testconfig.ini"

from gui.app import launch_app
from config import OMDB_API_KEY, PREPEND_EPISODE_TITLE_TO_EXTRAS, debug_print

def main():
    if OMDB_API_KEY == "key" or not OMDB_API_KEY.strip():
        print("❌ OMDB API key is missing. Please add it to the config.ini under [OMDb].")
        return
    # debug_print(f"value of prepend_episode_title_to_extras = {PREPEND_EPISODE_TITLE_TO_EXTRAS} / config.ini under [General].")
    launch_app()

if __name__ == "__main__":
    main()
