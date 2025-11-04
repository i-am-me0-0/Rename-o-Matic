import tkinter as tk
from typing import Callable, Any
import threading
from io import BytesIO
import requests
from PIL import Image, ImageTk


class YearMismatchPrompt(tk.Frame):
    def __init__(self, master: Any, filename: str, entry: dict, imdb_id: str, on_choice: Callable[[str], None] ):
        super().__init__(master)
        self.on_choice = on_choice
        self._poster_img = None
        self.filename = filename

        # Layout: left = poster, right = details + buttons
        top = tk.Frame(self)
        top.pack(fill='x', padx=8, pady=6)

        img_frame = tk.Frame(top, width=140, height=200)
        img_frame.pack(side='right', padx=(10, 10))
        img_frame.pack_propagate(False)
        self.img_label = tk.Label(img_frame, text="[No Image]", width=18, height=12)
        self.img_label.pack(fill='both', expand=True)

        details_frame = tk.Frame(top)
        details_frame.pack(side='left', fill='both', expand=True)

        tk.Label(details_frame, text="Year Mismatch: Movie Metadata", font=("Arial", 12)).pack(pady=(0, 6), anchor='w')
        msg = (
            f"Filename: {filename}\n"
            f"Title: {entry.get('title','')}\n"
            f"Year in metadata: {entry.get('year','')}\n"
            f"IMDb ID: {imdb_id}\n\nUse this ID?"
        )
        tk.Label(details_frame, text=msg, justify="left", anchor="w").pack(fill='x')

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)

        yes_btn = tk.Button(btn_frame, text="Yes", width=10, command=lambda: self._choose('yes'))
        yes_btn.pack(side="left", padx=5)
        no_btn = tk.Button(btn_frame, text="Skip", width=10, command=lambda: self._choose('no'))
        no_btn.pack(side="left", padx=5)

        rescrape_btn = tk.Button(btn_frame, text="Rescrape this movie", width=18, command=lambda: self._choose('rescrape'))
        rescrape_btn.pack(side="left", padx=5)

        # Add 'Use Existing Cache' button
        use_cache_btn = tk.Button(btn_frame, text="Use Existing Cache", width=18, command=lambda: self._choose('use_cache'))
        use_cache_btn.pack(side="left", padx=5)

        # Try to display poster image if available
        poster_url = entry.get('poster_url') if entry else None
        if not poster_url:
            try:
                from core.media_metadata_cache import get_entry as _get_entry
                meta = _get_entry(imdb_id)
                poster_url = meta.get('poster_url') if meta else None
            except Exception:
                poster_url = None

        if poster_url:
            def _download_and_set():
                try:
                    resp = requests.get(poster_url, timeout=6)
                    img = Image.open(BytesIO(resp.content)).resize((140, 200))
                    def _set_img():
                        try:
                            self._poster_img = ImageTk.PhotoImage(img)
                            self.img_label.configure(image=self._poster_img, text="")
                        except Exception:
                            pass
                    self.after(0, _set_img)
                except Exception:
                    pass
            t = threading.Thread(target=_download_and_set, daemon=True)
            t.start()

    def _open_cache_picker(self):
        # No longer used; picker is now opened from movies.py
        pass

    def _choose(self, action: str):
        try:
            self.on_choice(action)
        except Exception:
            pass
        # Destroy ourselves after signalling the parent so we don't leave orphaned frames
        try:
            self.destroy()
        except Exception:
            pass
