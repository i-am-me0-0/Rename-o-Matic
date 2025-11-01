# gui/preview.py
from actions import movies, series
from actions.series import plan_series_renames_with_gui_prompts
from pathlib import Path
from config import DEFAULT_INCLUDE, PLANNED_RENAMES_FILE
import json
import re

# Windows forbidden chars: \/:*?"<>|
def sanitize_path_component(component):
    # Remove illegal characters for Windows filenames/folders
    return re.sub(r'[\\/:*?"<>|]', ' -', component)

def validate_and_sanitize_path(path_str):
    # Split into parts, sanitize each, and rejoin
    # Special handling for Windows drive letters (e.g., D:\)
    # If path_str starts with a drive letter and backslash, preserve it
    match = re.match(r'^([A-Za-z]:\\)(.*)', path_str)
    if match:
        drive = match.group(1)
        rest = match.group(2)
        # Sanitize the rest
        parts = Path(rest).parts
        sanitized_parts = [sanitize_path_component(p) for p in parts]
        return drive + str(Path(*sanitized_parts))
    # Otherwise, use the original logic
    parts = Path(path_str).parts
    sanitized_parts = []
    # If first part is a drive letter (e.g., 'D:'), preserve it
    if parts and re.match(r'^[A-Za-z]:$', parts[0]):
        sanitized_parts.append(parts[0])
        parts = parts[1:]
    sanitized_parts += [sanitize_path_component(p) for p in parts]
    return str(Path(*sanitized_parts))


def generate_preview(root=None):
    import tkinter as tk
    from config import debug_print
    #debug_print("[DEBUG] generate_preview: started; root provided=" + str(bool(root)))
    # If a root is provided (AppRoot in GUI mode), use it so prompts can be frame-based.
    created_root = False
    if root is None:
        debug_print("[DEBUG] generate_preview: no root provided; creating temporary Tk root")
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        created_root = True
    planned = movies.plan_movie_renames() + plan_series_renames_with_gui_prompts(root)
    debug_print(f"[DEBUG] generate_preview: planned count={len(planned)}")
    if created_root:
        debug_print("[DEBUG] generate_preview: destroying temporary root")
        root.destroy()
    if not planned:
        print("⚠️ No files to rename.!!")
    else:
        print(f"📋 {len(planned)} renames planned.")

    # Write as JSON array of objects
    json_entries = []
    MAX_PATH = 260  # Windows max path length
    for item in planned:
        sanitized_to = validate_and_sanitize_path(item["dest"])
        if len(sanitized_to) > MAX_PATH:
            print(f"❌ Skipping: Destination path too long ({len(sanitized_to)} chars): {sanitized_to}")
            continue
        json_entries.append({
            "include": int(DEFAULT_INCLUDE),
            "type": item["type"],
            "from": item["src"],
            "to": sanitized_to
        })
    with open(PLANNED_RENAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(json_entries, f, indent=2, ensure_ascii=False)
    print(f"📄 Preview written to {PLANNED_RENAMES_FILE}. Review and edit as needed.")

def execute_from_preview():
    if not PLANNED_RENAMES_FILE.exists():
        print("❌ No preview file found. Run preview first.")
        return
    with open(PLANNED_RENAMES_FILE, encoding="utf-8") as f:
        try:
            planned = json.load(f)
        except Exception as e:
            print(f"❌ Failed to read planned renames: {e}")
            return
        for entry in planned:
            if int(entry.get("include", 0)) != 1:
                continue
            src = Path(entry["from"])
            dest = Path(entry["to"])
            item_type = entry["type"].lower()
            print(f"\n🔁 Renaming: {src} → {dest}")
            if item_type.capitalize() == "Movie":
                movies.rename_movie(src, dest)
            elif item_type.capitalize() == "Series":
                series.rename_series(src, dest)
            else:
                print(f"⚠️ Unknown type: {item_type}")
