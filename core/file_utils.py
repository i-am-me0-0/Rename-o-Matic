#file_utils.py 
from config import VIDEO_EXTENSIONS, SUBTITLE_EXTENSIONS, LANG_CODES
from pathlib import Path
import shutil

def is_video_file(file):
    return file.suffix.lower() in VIDEO_EXTENSIONS

def is_subtitle_file(file):
    return file.suffix.lower() in SUBTITLE_EXTENSIONS

def move_subtitles(original_path, dest_path):
    moved = []
    for code in LANG_CODES:
        suffix = f".{code}.srt" if code else ".srt"
        sub_file = original_path.with_suffix(suffix)
        if sub_file.exists():
            new_path = dest_path.with_suffix(suffix)
            shutil.move(str(sub_file), str(new_path))
            moved.append((sub_file, new_path))
    return moved
