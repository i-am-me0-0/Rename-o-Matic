# Blank slate planned renames generator for series
import json
from pathlib import Path
from config import SERIES_DIR, PLANNED_RENAMES_FILE
from core.file_utils import is_video_file

def main():
	planned = []
	# Recursively list all video files in SERIES_DIR
	for file in Path(SERIES_DIR).rglob("*"):
		if file.is_file() and is_video_file(file):
			planned.append({
				"include": 1,
				"type": "Series",
				"from": str(file.resolve()),
				"to": str(file.resolve())
				
			})
	with open(PLANNED_RENAMES_FILE, "w", encoding="utf-8") as f:
		json.dump(planned, f, indent=2, ensure_ascii=False)
	print(f"Planned renames written to {PLANNED_RENAMES_FILE} (blank slate, ready for manual editing)")

if __name__ == "__main__":
	main()
