import tkinter as tk
import re
from typing import Any, Dict, List, Optional
from actions.custom_imdb_web_poster_scraper import scrape_full_movie_metadata
from actions.omdb_gui_scraper import safe_download_image, safe_request, search_omdb, get_root, SEARCH_LIMIT
from config import ui_debug_print


class Picker(tk.Frame):
    def __init__(self, master: Any, original_line: str, search_title: str, results: List[Dict[str, Any]], source: Optional[str] = None):
        super().__init__(master)
        self.selection: Optional[dict[str, Any]] = None
        self.cancelled = False
        self.skipped = False
        # Use the app root for variable ownership to ensure wait_variable works
        root = get_root()
        self.search_term = tk.StringVar(root, value=search_title)
        self.results = results[:SEARCH_LIMIT]
        self.original_line = original_line
        # source indicates caller type: e.g. 'movie' or 'series'
        self.source = source
        # Variables used for parent communication (owned by root)
        self.done_var = tk.BooleanVar(root, value=False)

        # Build widgets on this Frame
        self.make_widgets()

        # Focus the search entry and log focus/grab state for diagnostics
        try:
            self.search_entry.focus_set()
        except Exception:
            pass
        try:
            cur_focus = root.focus_get()
            cur_grab = root.grab_current()
            ui_debug_print(f"[DBG] Picker.__init__: focus_get={cur_focus}, grab_current={cur_grab}")
        except Exception as e:
            ui_debug_print(f"[DBG] Picker.__init__: could not read focus/grab: {e}")

    def make_widgets(self):
        tk.Label(self, text=f"File/Folder: {self.original_line} | Type: {self.source or ''}", fg="gray", font=("Arial", 10, "italic"),
                 anchor="w", wraplength=500, justify="left").pack(fill='x', padx=5, pady=(5, 0))

        top_frame = tk.Frame(self)
        top_frame.pack(fill='x', padx=5, pady=5)

        # Keep a reference to the entry so we can focus it when needed.
        self.search_entry = tk.Entry(top_frame, textvariable=self.search_term, width=40)
        self.search_entry.pack(side='left', padx=(0, 5))
        self.search_entry.bind("<Return>", lambda event: self.manual_search())
        tk.Button(top_frame, text="Search Again", command=self.manual_search).pack(side='left')
        tk.Button(top_frame, text="Confirm Selection", command=self.confirm).pack(side='right')
        tk.Button(top_frame, text="Skip", fg="blue", command=self.skip).pack(side='right', padx=(5, 0))
        tk.Button(top_frame, text="Cancel", fg="red", command=self.cancel).pack(side='right', padx=(5, 10))

        self.result_frame = tk.Frame(self)
        self.result_frame.pack(fill='both', expand=True)
        self.show_results(self.results)

        # Ensure the search field has focus after initial rendering.
        try:
            self.search_entry.focus_set()
        except Exception:
            pass
        try:
            root = get_root()
            cur_focus = root.focus_get()
            cur_grab = root.grab_current()
            ui_debug_print(f"[DBG] Picker.make_widgets: after show_results focus_get={cur_focus}, grab_current={cur_grab}")
        except Exception as e:
            ui_debug_print(f"[DBG] Picker.make_widgets: could not read focus/grab: {e}")

    def show_results(self, results: List[Dict[str, Any]]):
        for widget in self.result_frame.winfo_children():
            widget.destroy()

        manual_imdb_id = None
        search_text = self.search_term.get().strip()
        if re.match(r"tt\d{7,}", search_text, re.I):
            manual_imdb_id = search_text

        if not results and manual_imdb_id:
            results = [{
                'Title': f"Manual IMDb ID entry: {manual_imdb_id}",
                'Year': '',
                'imdbID': manual_imdb_id,
                'Poster': None,
            }]

        for i, item in enumerate(results):
            frame = tk.Frame(self.result_frame, bd=1, relief="solid", padx=5, pady=5)
            frame.pack(fill='x', padx=5, pady=2)

            if item.get('Poster') and item['Poster'] != 'N/A':
                try:
                    img_tk = safe_download_image(item['Poster'])
                    if img_tk:
                        img_label = tk.Label(frame, image=img_tk)
                        refs = getattr(frame, '_img_refs', None)
                        if refs is None:
                            refs = []
                            setattr(frame, '_img_refs', refs)
                        refs.append(img_tk)
                        img_label.pack(side='left', padx=5)
                except Exception:
                    tk.Label(frame, text="[No Image]").pack(side='left', padx=5)
            else:
                tk.Label(frame, text="[No Image]").pack(side='left', padx=5)

            btn = tk.Radiobutton(
                frame,
                text=f"{item.get('Title', 'Unknown')} ({item.get('Year', 'N/A')})",
                value=item.get('imdbID'),
                indicatoron=False,
                width=40,
                command=lambda it=item: self.choose(it)
            )
            btn.pack(side='left', padx=10)

            if i == 0:
                self.selection = item
                btn.select()

        # Keep focus on the search entry so it's editable immediately after
        # results are displayed (important when reusing the picker repeatedly).
        try:
            self.search_entry.focus_set()
        except Exception:
            pass

    def choose(self, item: Dict[str, Any]):
        ui_debug_print(f"[DBG] Picker.choose called: selecting {item.get('imdbID')}")
        self.selection = item

    def manual_search(self):
        query = self.search_term.get().strip()
        if not query:
            return
        ui_debug_print(f"[DBG] Picker.manual_search: query='{query}'")
        self.results = safe_request(search_omdb, query, message=f"Searching for '{query}'...")
        ui_debug_print(f"[DBG] Picker.manual_search: got {len(self.results) if self.results else 0} results")
        self.show_results(self.results)

    def confirm(self):
        search_text = self.search_term.get().strip()
        ui_debug_print(f"[DBG] Picker.confirm called: search_text='{search_text}' selection before confirm={self.selection}")
        if re.match(r"tt\d{7,}", search_text, re.I):
            self.selection = {
                'Title': '',
                'Year': '',
                'imdbID': search_text,
                'Poster': None,
            }
            # Do not perform long-running scraping here on the GUI thread.
            # Let the caller (which created the Picker) perform any scraping or
            # metadata updates after it has read the selection. Setting
            # done_var allows the parent to read selection and then destroy
            # the Picker in a single, controlled place.
            self.done_var.set(True)
            ui_debug_print(f"[DBG] Picker.confirm: manual tt entry; done_var set")
        else:
            self.done_var.set(True)
            ui_debug_print(f"[DBG] Picker.confirm: done_var set; selection={self.selection}")

    def skip(self):
        self.selection = None
        self.skipped = True
        # Signal the parent that the user chose to skip; the parent will
        # destroy the Picker and continue. Do not destroy here or call
        # navigation methods from the callback.
        ui_debug_print("[DBG] Picker.skip called")
        self.done_var.set(True)

    def cancel(self):
        self.cancelled = True
        # Do not navigate away or destroy the Picker from inside the
        # callback. Signal the parent to handle navigation and cleanup.
        ui_debug_print("[DBG] Picker.cancel called")
        self.done_var.set(True)
