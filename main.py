# main.py (entry point only)

import sys
import os
if len(sys.argv) > 1 and sys.argv[1].lower() == "test":
    os.environ["RENAMER_CONFIG_FILE"] = "testconfig.ini"
    os.environ["RENAMER_TEST_MODE"] = "1"

# In test mode, install a global exception hook to print tracebacks to console
if os.environ.get("RENAMER_TEST_MODE") == "1":
    import traceback
    def _ex_hook(exc_type, exc, tb):
        print("UNCAUGHT EXCEPTION:")
        traceback.print_exception(exc_type, exc, tb)
    sys.excepthook = _ex_hook
from gui.app import launch_app
from gui.api_key_prompt import prompt_for_api_key
from config import OMDB_API_KEY, CONFIG_FILE
import tkinter as tk
from tkinter import messagebox

def main():
    if OMDB_API_KEY == "key" or not OMDB_API_KEY.strip():
        print("⚠️  OMDb API key is missing.")
        if not prompt_for_api_key(CONFIG_FILE):
            print("❌ API key is required. Exiting.")
            return
        print("✅ API key saved.")
        # Show restart message
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Success", "API key saved successfully.\n\nPlease restart the application.")
        root.destroy()
        return
    # debug_print(f"value of prepend_episode_title_to_extras = {PREPEND_EPISODE_TITLE_TO_EXTRAS} / config.ini under [General].")
    launch_app()

if __name__ == "__main__":
    main()
