import tkinter as tk
from typing import Any, Callable, List, Tuple
import threading
from io import BytesIO
try:
    import requests
    from PIL import Image, ImageTk
except Exception:
    requests = None
    Image = None

from core.media_metadata_cache import load_metadata


class ExistingCachePickerFrame(tk.Frame):
    """Frame that lets the user pick an existing media-cache entry to reuse.

    The frame will search the local media metadata cache for titles matching
    the provided folder/show name and present a list with small poster thumbnails.
    """
    def __init__(self, master: Any, name: str, conflicting_id: str, on_choice: Callable[[str], None], filter_type: str = None):
        super().__init__(master)
        self.on_choice = on_choice
        self._poster_img = None
        self.matches: List[Tuple[str, str, dict]] = []  # (label, imdb_id, meta)
        self.name = name
        self.filter_type = filter_type.lower() if filter_type else None

        top = tk.Frame(self)
        top.pack(fill='both', expand=True, padx=8, pady=6)

        left = tk.Frame(top)
        left.pack(side='left', fill='y', padx=(0,8))

        self.img_label = tk.Label(left, text="[No Image]", width=18, height=12)
        self.img_label.pack()

        right = tk.Frame(top)
        right.pack(side='left', fill='both', expand=True)

        display_name = name if name else '(Unknown)'
        tk.Label(right, text=f"File: {display_name}", font=("Arial", 11, "bold")).pack(anchor='w')

        # Listbox with scrollbar
        list_frame = tk.Frame(right)
        list_frame.pack(fill='both', expand=True, pady=(6,0))
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')
        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, selectmode=tk.SINGLE)
        self.listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.listbox.yview)

        # Buttons
        btnf = tk.Frame(self)
        btnf.pack(pady=8)
        tk.Button(btnf, text="Use Selected", width=14, command=self._use_selected).pack(side='left', padx=6)
        tk.Button(btnf, text="Enter ID Manually", width=16, command=self._prompt_manual).pack(side='left', padx=6)
        tk.Button(btnf, text="Cancel", width=10, command=self._cancel).pack(side='left', padx=6)

        # Populate matches in background
        self._load_matches_async(display_name)

        # When selection changes, show poster
        self.listbox.bind('<<ListboxSelect>>', lambda e: self._on_select())

    def _normalize(self, s: str) -> str:
        try:
            import re, unicodedata
            s2 = unicodedata.normalize('NFKD', str(s) or '')
            s2 = re.sub(r"[^\n\w\s]", ' ', s2).lower()
            s2 = re.sub(r"\s+", ' ', s2).strip()
            return s2
        except Exception:
            return (s or '').lower().strip()

    def _load_matches_async(self, name: str):
        def _worker():
            try:
                needle = self._normalize(name or '')
                data = load_metadata()
                def type_matches(meta_type):
                    if not self.filter_type:
                        return True
                    if not meta_type:
                        return False
                    return str(meta_type).strip().lower() == self.filter_type

                # 1. Try strict match (needle in normalized title)
                for mid, meta in data.items():
                    if not type_matches(meta.get('type')):
                        continue
                    title = (meta.get('title') or '')
                    if not title:
                        continue
                    if needle and needle in self._normalize(title):
                        year = meta.get('year') or meta.get('end_year') or ''
                        label = f"{title} ({year}) [{mid}]"
                        self.matches.append((label, mid, meta))

                # 2. If nothing found, try looser match: substring of folder words
                if not self.matches and name:
                    parts = [p for p in name.split() if len(p) > 3]
                    for mid, meta in data.items():
                        if not type_matches(meta.get('type')):
                            continue
                        title = (meta.get('title') or '')
                        if not title:
                            continue
                        norm = self._normalize(title)
                        if any(self._normalize(p) in norm for p in parts):
                            year = meta.get('year') or meta.get('end_year') or ''
                            label = f"{title} ({year}) [{mid}]"
                            self.matches.append((label, mid, meta))

                # 3. If still nothing, show all entries of the correct type
                if not self.matches:
                    for mid, meta in data.items():
                        if not type_matches(meta.get('type')):
                            continue
                        title = (meta.get('title') or '')
                        if not title:
                            continue
                        year = meta.get('year') or meta.get('end_year') or ''
                        label = f"{title} ({year}) [{mid}]"
                        self.matches.append((label, mid, meta))
            except Exception:
                pass
            # update UI on main thread
            try:
                self.after(0, self._populate_listbox)
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _populate_listbox(self):
        self.listbox.delete(0, tk.END)
        for lbl, mid, meta in self.matches:
            self.listbox.insert(tk.END, lbl)

    def _on_select(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        _, mid, meta = self.matches[idx]
        poster_url = meta.get('poster_url') if meta else None
        if poster_url and requests and Image:
            def _dl():
                try:
                    resp = requests.get(poster_url, timeout=6)
                    img = Image.open(BytesIO(resp.content)).resize((140,200))
                    def _set_img():
                        try:
                            self._poster_img = ImageTk.PhotoImage(img)
                            self.img_label.configure(image=self._poster_img, text='')
                        except Exception:
                            pass
                    self.after(0, _set_img)
                except Exception:
                    pass
            threading.Thread(target=_dl, daemon=True).start()
        else:
            self.img_label.configure(text='[No Image]', image='')

    def _use_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        _, mid, meta = self.matches[idx]
        # Return only the IMDb ID string to the callback
        try:
            self.on_choice(mid)
        except Exception:
            pass
        # If in a modal dialog, close the parent window
        try:
            self.winfo_toplevel().destroy()
        except Exception:
            pass

    def _prompt_manual(self):
        # ask for manual imdb id in small dialog
        top = tk.Toplevel(self)
        top.title('Enter IMDb ID')
        tk.Label(top, text='Enter IMDb ID (e.g. tt1234567)').pack(padx=8, pady=6)
        entry = tk.Entry(top, width=24)
        entry.pack(padx=8, pady=6)
        def _ok():
            val = entry.get().strip()
            if val:
                try:
                    self.on_choice(val)
                except Exception:
                    pass
            try:
                top.destroy()
            except Exception:
                pass
            # If in a modal dialog, close the parent window
            try:
                self.winfo_toplevel().destroy()
            except Exception:
                pass
        tk.Button(top, text='OK', command=_ok).pack(pady=6)

    def _cancel(self):
        try:
            self.on_choice(None)
        except Exception:
            pass
        # If in a modal dialog, close the parent window
        try:
            self.winfo_toplevel().destroy()
        except Exception:
            pass
