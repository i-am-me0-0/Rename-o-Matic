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
    import traceback
    planned = []
    # Call planners separately so we can identify which one raises
    try:
        movie_planned = movies.plan_movie_renames()
        planned.extend(movie_planned)
    except Exception as e:
        debug_print(f"[ERROR] generate_preview: movies.plan_movie_renames() raised: {e}")
        debug_print(traceback.format_exc())
        raise
    try:
        series_planned = plan_series_renames_with_gui_prompts(root)
        planned.extend(series_planned)
    except Exception as e:
        debug_print(f"[ERROR] generate_preview: plan_series_renames_with_gui_prompts() raised: {e}")
        debug_print(traceback.format_exc())
        raise
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
    for idx, item in enumerate(planned):
        # Defensive: ensure item is a dict with expected keys
        if not isinstance(item, dict):
            debug_print(f"[ERROR] generate_preview: planned[{idx}] is not a dict (type={type(item).__name__}): {repr(item)} -- skipping")
            continue
        if not all(k in item for k in ("dest", "src", "type")):
            debug_print(f"[ERROR] generate_preview: planned[{idx}] missing keys: {item} -- skipping")
            continue
        try:
            sanitized_to = validate_and_sanitize_path(item["dest"])
        except Exception as e:
            debug_print(f"[ERROR] generate_preview: failed to sanitize dest for planned[{idx}] ({item}): {e} -- skipping")
            continue
        # Further normalize common punctuation artifacts introduced during naming
        try:
            # collapse repeated hyphens into a single spaced hyphen
            sanitized_to = re.sub(r"\s*-\s*-\s*", " - ", sanitized_to)
            # convert patterns like "-!" (hyphen immediately before exclamation) to just '!'
            sanitized_to = re.sub(r"\s*-\s*!", "!", sanitized_to)
            # collapse spaced duplicate punctuation like '! !' or '. .' to single punctuation
            sanitized_to = re.sub(r'([!?.])(?:\s+\1)+', r"\1", sanitized_to)
            # collapse multiple spaces again
            sanitized_to = re.sub(r"\s{2,}", " ", sanitized_to)
        except Exception:
            pass
        # Defensive: skip entries where source and destination are the same
        try:
            from pathlib import Path as _P
            try:
                if _P(item["src"]).resolve() == _P(sanitized_to).resolve():
                    #debug_print(f"[DEBUG] generate_preview: Skipping entry with identical src/dest (resolved): {item['src']}")
                    continue
            except Exception:
                # Fallback to string comparison if resolve() fails for any reason
                if str(item.get("src", "")) == str(sanitized_to):
                    #debug_print(f"[DEBUG] generate_preview: Skipping entry with identical src/dest (string): {item.get('src')}")
                    continue
        except Exception:
            # Any unexpected error here should not block writing other entries
            debug_print(f"[WARN] generate_preview: error while comparing src/dest for planned[{idx}] -- continuing: {item}")
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
