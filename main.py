# main.py (entry point only)
from config import OMDB_API_KEY
from gui.app import launch_app

def main():
    if OMDB_API_KEY == "key" or not OMDB_API_KEY.strip():
        print("❌ OMDB API key is missing. Please add it to the config.ini under [General].")
        return
    launch_app()

if __name__ == "__main__":
    main()
