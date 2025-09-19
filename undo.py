#undo.py
import shutil
from config import LOG_FILE
from pathlib import Path


def log_rename(original, new, subtitles=None):
    with open(LOG_FILE, 'a', encoding='utf-8') as log:
        log.write(f"{original} -> {new}\n")
        if subtitles:
            for old_sub, new_sub in subtitles:
                log.write(f"  Sub: {old_sub} -> {new_sub}\n")



def undo_last_operations():
    if not LOG_FILE.exists():
        print("❌ No log file found.")
        return

    with open(LOG_FILE, "r", encoding="utf-8") as log:
        lines = log.readlines()[::-1]

    for line in lines:
        if "->" not in line:
            continue
        if "Sub:" in line:
            parts = line.replace("Sub:", "").strip().split(" -> ")
        else:
            parts = line.strip().split(" -> ")
        if len(parts) != 2:
            continue

        src = Path(parts[1])
        dst = Path(parts[0])
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            print(f"↩️ Restored {src} -> {dst}")

    print("✅ Undo complete.")
