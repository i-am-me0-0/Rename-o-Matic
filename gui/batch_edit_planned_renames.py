# # gui/batch_edit_planned_renames.py
# import tkinter as tk
# from tkinter import ttk, messagebox
# import json
# import os
# from config import PLANNED_RENAMES_FILE


# class CollapsibleFrame(tk.Frame):
#     """A collapsible container with a header and a body."""

#     def __init__(self, master, text="", *args, **kwargs):
#         super().__init__(master, *args, **kwargs)
#         self.showing = tk.BooleanVar(value=True)

#         self.header = tk.Frame(self)
#         self.header.pack(fill="x")

#         self.toggle_btn = ttk.Checkbutton(
#             self.header,
#             text=text,
#             variable=self.showing,
#             command=self.toggle,
#             style="Toolbutton",
#         )
#         self.toggle_btn.pack(side="left", anchor="w")

#         self.body = tk.Frame(self)
#         self.body.pack(fill="both", expand=True)

#     def toggle(self):
#         if self.showing.get():
#             self.body.pack(fill="both", expand=True)
#         else:
#             self.body.forget()


# class BatchEditPlannedRenames(tk.Frame):
#     def __init__(self, master, *args, **kwargs):
#         super().__init__(master, *args, **kwargs)
#         self.master = master
#         self.renames = self.load_renames()
#         self.entry_widgets = {}  # map idx → (include_var, entry_widget)
#         self.build_ui()

#     # ---------------- File Handling ----------------
#     def load_renames(self):
#         if not os.path.exists(PLANNED_RENAMES_FILE):
#             return []
#         with open(PLANNED_RENAMES_FILE, "r", encoding="utf-8") as f:
#             return json.load(f)

#     def save_renames(self):
#         # Update renames from widgets
#         for idx, (inc_var, entry) in self.entry_widgets.items():
#             self.renames[idx]["include"] = inc_var.get()
#             self.renames[idx]["to"] = entry.get()

#         with open(PLANNED_RENAMES_FILE, "w", encoding="utf-8") as f:
#             json.dump(self.renames, f, indent=2, ensure_ascii=False)
#         messagebox.showinfo("Saved", "Planned renames saved.")

#     # ---------------- UI ----------------
#     def build_ui(self):
#         tk.Label(self, text="Batch Edit Planned Renames", font=("Arial", 16)).pack(pady=10)

#         # Base Directory
#         top_frame = tk.Frame(self)
#         tk.Label(top_frame, text="Base Directory:").pack(side="left", padx=5)
#         self.base_dir_var = tk.StringVar()
#         tk.Entry(top_frame, textvariable=self.base_dir_var, width=80).pack(side="left", padx=5)
#         top_frame.pack(pady=5, fill="x")

#         # Main scrollable canvas
#         canvas = tk.Canvas(self)
#         scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
#         self.scroll_frame = tk.Frame(canvas)

#         self.scroll_frame.bind(
#             "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
#         )
#         canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
#         canvas.configure(yscrollcommand=scrollbar.set)

#         canvas.pack(side="left", fill="both", expand=True)
#         scrollbar.pack(side="right", fill="y")

#         # Buttons
#         btn_frame = tk.Frame(self)
#         btn_frame.pack(pady=10)
#         tk.Button(btn_frame, text="Set Include for All", command=self.set_include_for_all).pack(
#             side="left", padx=5
#         )
#         tk.Button(btn_frame, text="Save Changes", command=self.save_renames).pack(
#             side="left", padx=5
#         )
#         tk.Button(btn_frame, text="Reload", command=self.reload_tree).pack(
#             side="left", padx=5
#         )

#         self.populate_tree()

#     def get_grouping(self, entry):
#         from_path = entry.get("from", "")
#         parts = from_path.replace("\\", "/").split("/")
#         series = ""
#         season = ""
#         for part in parts:
#             if "[tt" in part:
#                 series = part
#             if part.lower().startswith("season"):
#                 season = part
#         return series, season

#     def populate_tree(self):
#         # Clear old
#         for widget in self.scroll_frame.winfo_children():
#             widget.destroy()
#         self.entry_widgets.clear()

#         # Group entries
#         movies = []
#         series_map = {}

#         for idx, entry in enumerate(self.renames):
#             series, season = self.get_grouping(entry)
#             if not series:
#                 movies.append((idx, entry))
#             else:
#                 series_map.setdefault(series, {}).setdefault(season, []).append((idx, entry))

#         # Movies section
#         if movies:
#             movies_frame = CollapsibleFrame(self.scroll_frame, text="Movies")
#             movies_frame.pack(fill="x", pady=2, anchor="w")
#             for idx, entry in movies:
#                 self.add_entry_row(movies_frame.body, idx, entry)

#         # Series section
#         if series_map:
#             series_root = CollapsibleFrame(self.scroll_frame, text="Series")
#             series_root.pack(fill="x", pady=2, anchor="w")
#             for series, seasons in series_map.items():
#                 series_frame = CollapsibleFrame(series_root.body, text=series)
#                 series_frame.pack(fill="x", padx=20, pady=2, anchor="w")
#                 for season, items in seasons.items():
#                     season_frame = CollapsibleFrame(series_frame.body, text=season)
#                     season_frame.pack(fill="x", padx=40, pady=1, anchor="w")
#                     for idx, entry in items:
#                         self.add_entry_row(season_frame.body, idx, entry)

#     def add_entry_row(self, parent, idx, entry):
#         row = tk.Frame(parent)
#         row.pack(fill="x", padx=20, pady=1)

#         inc_var = tk.IntVar(value=entry.get("include", 0))
#         chk = tk.Checkbutton(row, variable=inc_var)
#         chk.pack(side="left")

#         txt = tk.Entry(row, width=100)
#         txt.insert(0, entry.get("to", ""))
#         txt.pack(side="left", fill="x", expand=True)

#         self.entry_widgets[idx] = (inc_var, txt)

#     def set_include_for_all(self):
#         if not self.renames:
#             return
#         val = messagebox.askyesno("Set Include", "Set include=1 for all? (No = set 0)")
#         new_val = 1 if val else 0
#         for inc_var, _ in self.entry_widgets.values():
#             inc_var.set(new_val)

#     def reload_tree(self):
#         self.renames = self.load_renames()
#         self.populate_tree()


# # For standalone testing
# if __name__ == "__main__":
#     root = tk.Tk()
#     root.title("Batch Edit Planned Renames")
#     frame = BatchEditPlannedRenames(root)
#     frame.pack(fill="both", expand=True)
#     root.geometry("1200x800")
#     root.mainloop()

# 2nd try
# # gui/batch_edit_planned_renames.py
# import tkinter as tk
# from tkinter import ttk, messagebox
# import json
# import os
# from config import PLANNED_RENAMES_FILE


# class CollapsibleFrame(tk.Frame):
#     """A collapsible container with a header and a body."""

#     def __init__(self, master, text="", *args, **kwargs):
#         super().__init__(master, *args, **kwargs)
#         self.showing = tk.BooleanVar(value=True)

#         self.header = tk.Frame(self)
#         self.header.pack(fill="x")

#         self.toggle_btn = ttk.Checkbutton(
#             self.header,
#             text=text,
#             variable=self.showing,
#             command=self.toggle,
#             style="Toolbutton",
#         )
#         self.toggle_btn.pack(side="left", anchor="w")

#         self.body = tk.Frame(self)
#         self.body.pack(fill="both", expand=True)

#     def toggle(self):
#         if self.showing.get():
#             self.body.pack(fill="both", expand=True)
#         else:
#             self.body.forget()


# class BatchEditPlannedRenames(tk.Frame):
#     def __init__(self, master, *args, **kwargs):
#         super().__init__(master, *args, **kwargs)
#         self.master = master
#         self.renames = self.load_renames()
#         self.entry_widgets = {}  # map idx → (include_var, entry_widget)
#         self.build_ui()

#     # ---------------- File Handling ----------------
#     def load_renames(self):
#         if not os.path.exists(PLANNED_RENAMES_FILE):
#             return []
#         with open(PLANNED_RENAMES_FILE, "r", encoding="utf-8") as f:
#             return json.load(f)

#     def save_renames(self):
#         # Update renames from widgets
#         for idx, (inc_var, entry) in self.entry_widgets.items():
#             self.renames[idx]["include"] = inc_var.get()
#             self.renames[idx]["to"] = entry.get()

#         with open(PLANNED_RENAMES_FILE, "w", encoding="utf-8") as f:
#             json.dump(self.renames, f, indent=2, ensure_ascii=False)
#         messagebox.showinfo("Saved", "Planned renames saved.")

#     # ---------------- UI ----------------
#     def build_ui(self):
#         tk.Label(self, text="Batch Edit Planned Renames", font=("Arial", 16)).pack(pady=10)

#         # Main scrollable canvas
#         canvas = tk.Canvas(self)
#         scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
#         self.scroll_frame = tk.Frame(canvas)

#         self.scroll_frame.bind(
#             "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
#         )
#         canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
#         canvas.configure(yscrollcommand=scrollbar.set)

#         canvas.pack(side="left", fill="both", expand=True)
#         scrollbar.pack(side="right", fill="y")

#         # Buttons
#         btn_frame = tk.Frame(self)
#         btn_frame.pack(pady=10)
#         tk.Button(btn_frame, text="Set Include for All", command=self.set_include_for_all).pack(
#             side="left", padx=5
#         )
#         tk.Button(btn_frame, text="Save Changes", command=self.save_renames).pack(
#             side="left", padx=5
#         )
#         tk.Button(btn_frame, text="Reload", command=self.reload_tree).pack(
#             side="left", padx=5
#         )

#         self.populate_tree()

#     def split_path(self, path):
#         """Normalize and split a path into parts"""
#         return path.replace("\\", "/").split("/")

#     def populate_tree(self):
#         # Clear old
#         for widget in self.scroll_frame.winfo_children():
#             widget.destroy()
#         self.entry_widgets.clear()

#         # Group entries by root path (first directory segment)
#         roots = {}

#         for idx, entry in enumerate(self.renames):
#             from_path = entry.get("from", "")
#             parts = self.split_path(from_path)

#             if not parts:
#                 continue

#             root = parts[0]  # e.g. "media"
#             roots.setdefault(root, []).append((idx, entry))

#         # Build explorer-style tree
#         for root, items in roots.items():
#             root_frame = CollapsibleFrame(self.scroll_frame, text=root + "/")
#             root_frame.pack(fill="x", pady=2, anchor="w")

#             # Sub-group into Movies / Series
#             movies_frame = CollapsibleFrame(root_frame.body, text="Movies/")
#             series_frame = CollapsibleFrame(root_frame.body, text="Series/")

#             has_movies = False
#             has_series = False

#             for idx, entry in items:
#                 etype = entry.get("type", "")
#                 from_path = entry.get("from", "")
#                 parts = self.split_path(from_path)

#                 # Drop root (first part)
#                 rel_parts = parts[1:]

#                 if etype.lower() == "movie":
#                     has_movies = True
#                     self.add_movie_entry(movies_frame.body, rel_parts, idx, entry)
#                 elif etype.lower() == "series":
#                     has_series = True
#                     self.add_series_entry(series_frame.body, rel_parts, idx, entry)

#             if has_movies:
#                 movies_frame.pack(fill="x", padx=20, pady=2, anchor="w")
#             if has_series:
#                 series_frame.pack(fill="x", padx=20, pady=2, anchor="w")

#     def add_movie_entry(self, parent, rel_parts, idx, entry):
#         """
#         Add a movie to the explorer tree.
#         rel_parts: e.g. ["movies","Men In Black (1, 2, 3)","Men in Black (1997).mkv"]
#         """
#         # Walk down until last element (filename)
#         frame = parent
#         for folder in rel_parts[:-1]:
#             # Reuse or create subfolder collapsible frame
#             found = None
#             for child in frame.winfo_children():
#                 if isinstance(child, CollapsibleFrame) and child.toggle_btn.cget("text") == folder + "/":
#                     found = child
#                     break
#             if not found:
#                 found = CollapsibleFrame(frame, text=folder + "/")
#                 found.pack(fill="x", padx=20, pady=1, anchor="w")
#             frame = found.body

#         # Last part = filename (editable leaf)
#         filename = rel_parts[-1]
#         self.add_entry_row(frame, idx, entry, filename)

#     def add_series_entry(self, parent, rel_parts, idx, entry):
#         """
#         Add a series entry to the explorer tree.
#         rel_parts: e.g. ["series","Knight Rider [tt0083437]","Season 01","Episode.mkv"]
#         """
#         frame = parent
#         for folder in rel_parts[:-1]:
#             found = None
#             for child in frame.winfo_children():
#                 if isinstance(child, CollapsibleFrame) and child.toggle_btn.cget("text") == folder + "/":
#                     found = child
#                     break
#             if not found:
#                 found = CollapsibleFrame(frame, text=folder + "/")
#                 found.pack(fill="x", padx=20, pady=1, anchor="w")
#             frame = found.body

#         filename = rel_parts[-1]
#         self.add_entry_row(frame, idx, entry, filename)

#     def add_entry_row(self, parent, idx, entry, filename):
#         row = tk.Frame(parent)
#         row.pack(fill="x", padx=20, pady=1)

#         inc_var = tk.IntVar(value=entry.get("include", 0))
#         chk = tk.Checkbutton(row, variable=inc_var)
#         chk.pack(side="left")

#         txt = tk.Entry(row, width=100)
#         txt.insert(0, entry.get("to", filename))
#         txt.pack(side="left", fill="x", expand=True)

#         self.entry_widgets[idx] = (inc_var, txt)

#     def set_include_for_all(self):
#         if not self.renames:
#             return
#         val = messagebox.askyesno("Set Include", "Set include=1 for all? (No = set 0)")
#         new_val = 1 if val else 0
#         for inc_var, _ in self.entry_widgets.values():
#             inc_var.set(new_val)

#     def reload_tree(self):
#         self.renames = self.load_renames()
#         self.populate_tree()


# # For standalone testing
# if __name__ == "__main__":
#     root = tk.Tk()
#     root.title("Batch Edit Planned Renames")
#     frame = BatchEditPlannedRenames(root)
#     frame.pack(fill="both", expand=True)
#     root.geometry("1200x800")
#     root.mainloop()

#3rd try
# gui/batch_edit_planned_renames.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
from config import PLANNED_RENAMES_FILE


class CollapsibleFrame(tk.Frame):
    """A collapsible container with a header and a body."""

    def __init__(self, master, text="", *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.showing = tk.BooleanVar(value=True)

        self.header = tk.Frame(self)
        self.header.pack(fill="x")

        self.toggle_btn = ttk.Checkbutton(
            self.header,
            text=text,
            variable=self.showing,
            command=self.toggle,
            style="Toolbutton",
        )
        self.toggle_btn.pack(side="left", anchor="w")

        self.body = tk.Frame(self)
        self.body.pack(fill="both", expand=True)

    def toggle(self):
        if self.showing.get():
            self.body.pack(fill="both", expand=True)
        else:
            self.body.forget()


class BatchEditPlannedRenames(tk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.master = master
        self.renames = self.load_renames()
        self.entry_widgets = {}  # map idx → (include_var, entry_widget, base_dir)
        self.build_ui()

    # ---------------- File Handling ----------------
    def load_renames(self):
        if not os.path.exists(PLANNED_RENAMES_FILE):
            return []
        with open(PLANNED_RENAMES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_renames(self):
        # Update renames from widgets
        for idx, (inc_var, entry, base_dir) in self.entry_widgets.items():
            self.renames[idx]["include"] = inc_var.get()

            # reconstruct full "to" path
            rel_name = entry.get().strip()
            self.renames[idx]["to"] = os.path.join(base_dir, rel_name).replace("\\", "/")

        with open(PLANNED_RENAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.renames, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Saved", "Planned renames saved.")

    # ---------------- UI ----------------
    def build_ui(self):
        tk.Label(self, text="Batch Edit Planned Renames", font=("Arial", 16)).pack(pady=10)

        # Main scrollable canvas
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas)

        self.scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        # inside build_ui(), after canvas.configure(yscrollcommand=scrollbar.set)
        from gui.scroll_utils import bind_mousewheel_scrolling

        # Enable scrolling when the mouse is over the canvas:
        bind_mousewheel_scrolling(canvas)

        # If instead you *only* want to allow scrolling when keyboard focus is inside self.scroll_frame,
        # call:
        # bind_mousewheel_scrolling(canvas, widget=self.scroll_frame, require_focus=True)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Set Include for All", command=self.set_include_for_all).pack(
            side="left", padx=5
        )
        tk.Button(btn_frame, text="Save Changes", command=self.save_renames).pack(
            side="left", padx=5
        )
        tk.Button(btn_frame, text="Reload", command=self.reload_tree).pack(
            side="left", padx=5
        )

        self.populate_tree()

    def split_path(self, path):
        """Normalize and split a path into parts"""
        return path.replace("\\", "/").split("/")

    def populate_tree(self):
        # Clear old
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.entry_widgets.clear()

        # Top-level: Movies/ and Series/
        movies_top = CollapsibleFrame(self.scroll_frame, text="Movies/")
        movies_top.pack(fill="x", pady=2, anchor="w")

        series_top = CollapsibleFrame(self.scroll_frame, text="Series/")
        series_top.pack(fill="x", pady=2, anchor="w")

        # Group entries by type + root
        grouped = {"movie": {}, "series": {}}

        for idx, entry in enumerate(self.renames):
            to_path = entry.get("to", "")
            parts = self.split_path(to_path)
            if not parts:
                continue

            etype = entry.get("type", "").lower()
            root = parts[0]  # e.g. "media"

            grouped.setdefault(etype, {}).setdefault(root, []).append((idx, entry))

        # Build Movies tree
        for root, items in grouped.get("movie", {}).items():
            root_frame = CollapsibleFrame(movies_top.body, text=root + "/")
            root_frame.pack(fill="x", padx=20, pady=2, anchor="w")

            for idx, entry in items:
                rel_parts = self.split_path(entry["to"])[1:]  # drop root
                self.add_entry(root_frame.body, rel_parts, idx, entry)

        # Build Series tree
        for root, items in grouped.get("series", {}).items():
            root_frame = CollapsibleFrame(series_top.body, text=root + "/")
            root_frame.pack(fill="x", padx=20, pady=2, anchor="w")

            for idx, entry in items:
                rel_parts = self.split_path(entry["to"])[1:]  # drop root
                self.add_entry(root_frame.body, rel_parts, idx, entry)

    def add_entry(self, parent, rel_parts, idx, entry):
        """
        Add an entry into the tree explorer, creating folders as needed.
        rel_parts: path parts *after root*
        """
        frame = parent
        for folder in rel_parts[:-1]:
            found = None
            for child in frame.winfo_children():
                if isinstance(child, CollapsibleFrame) and child.toggle_btn.cget("text") == folder + "/":
                    found = child
                    break
            if not found:
                found = CollapsibleFrame(frame, text=folder + "/")
                found.pack(fill="x", padx=20, pady=1, anchor="w")
            frame = found.body

        # Last part = filename
        filename = rel_parts[-1]

        # Derive base dir (everything except filename)
        base_dir = os.path.dirname(entry["to"].replace("\\", "/"))
        rel_name = os.path.basename(entry["to"].replace("\\", "/"))

        row = tk.Frame(frame)
        row.pack(fill="x", padx=20, pady=1)

        inc_var = tk.IntVar(value=entry.get("include", 0))
        chk = tk.Checkbutton(row, variable=inc_var)
        chk.pack(side="left")

        txt = tk.Entry(row, width=100)
        txt.insert(0, rel_name)  # ✅ only filename shown
        txt.pack(side="left", fill="x", expand=True)

        self.entry_widgets[idx] = (inc_var, txt, base_dir)

    def set_include_for_all(self):
        if not self.renames:
            return
        val = messagebox.askyesno("Set Include", "Set include=1 for all? (No = set 0)")
        new_val = 1 if val else 0
        for inc_var, _, _ in self.entry_widgets.values():
            inc_var.set(new_val)

    def reload_tree(self):
        self.renames = self.load_renames()
        self.populate_tree()


# For standalone testing
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Batch Edit Planned Renames")
    frame = BatchEditPlannedRenames(root)
    frame.pack(fill="both", expand=True)
    root.geometry("1200x800")
    root.mainloop()
