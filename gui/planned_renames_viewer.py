import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font
import os
import json
from config import PLANNED_RENAMES_FILE, MOVIES_DIR, SERIES_DIR

def get_relative_path(path):
    for base in (str(MOVIES_DIR), str(SERIES_DIR)):
        if path.startswith(base):
            return os.path.relpath(path, base)
    return path

def parse_planned_renames(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, encoding="utf-8") as f:
        try:
            data = json.load(f)
            return [
                {
                    "include": int(entry.get("include", 0)),
                    "type": entry.get("type", ""),
                    "from": entry.get("from", ""),
                    "to": entry.get("to", "")
                }
                for entry in data
            ]
        except Exception as e:
            print(f"Error parsing planned_renames.json: {e}")
            return []

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None

    def show(self, x, y):
        if self.tipwindow or not self.text:
            return
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        # Calculate screen and tooltip size to keep on screen
        tw.update_idletasks()
        screen_width = tw.winfo_screenwidth()
        screen_height = tw.winfo_screenheight()
        # Create label first to measure
        label = tk.Label(tw, text=self.text, bg="#ffffe0", fg="#222", font=("Consolas", 10), justify="left", relief="solid", borderwidth=1, wraplength=600)
        label.pack(ipadx=1)
        tw.update_idletasks()
        tip_width = tw.winfo_width()
        tip_height = tw.winfo_height()
        # Adjust x/y if tooltip would go off screen
        if x + tip_width > screen_width:
            x = screen_width - tip_width - 10
        if y + tip_height > screen_height:
            y = screen_height - tip_height - 10
        tw.wm_geometry(f"+{x}+{y}")
        label.bind("<Button-1>", lambda e: tw.destroy())  # Hide on click

    def hide(self):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

class PlannedRenamesFrame(tk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.tooltip = None
        self.preview_label = tk.Label(self, text="", font=("Consolas", 10), bg="#ffffe0", anchor="w", relief="groove")
        self.preview_label.pack(side="top", fill="x", padx=2, pady=(2,0))
        self.preview_label.pack_forget()
        self.planned_renames = parse_planned_renames(str(PLANNED_RENAMES_FILE))
        # Calculate column widths
        include_vals = ["☑" if e["include"] else "☐" for e in self.planned_renames]
        include_header = "Include"
        include_font = font.Font()
        include_width = max([include_font.measure(val) for val in include_vals] + [include_font.measure(include_header)]) + 24
        type_vals = [e["type"] for e in self.planned_renames]
        type_header = "Type"
        type_font = font.Font()
        type_width = max([type_font.measure(val) for val in type_vals] + [type_font.measure(type_header)]) + 24
        columns = ("Include", "From", "To", "Type")
        tree_frame = tk.Frame(self)
        tree_frame.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("Include", text="Include")
        self.tree.heading("From", text="Current Name (relative)")
        self.tree.heading("To", text="Planned Name (relative)")
        self.tree.heading("Type", text="Type")
        self.tree.column("Include", width=include_width, minwidth=include_width, stretch=False, anchor="center")
        self.tree.column("Type", width=type_width, minwidth=type_width, stretch=False, anchor="center")
        self.tree.column("From", width=200, minwidth=80, stretch=True)
        self.tree.column("To", width=200, minwidth=80, stretch=True)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        for idx, entry in enumerate(self.planned_renames):
            from_rel = get_relative_path(entry["from"])
            to_rel = get_relative_path(entry["to"])
            checked = "☑" if entry["include"] else "☐"
            self.tree.insert("", "end", iid=idx, values=(checked, from_rel, to_rel, entry["type"]))
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Motion>", self.on_tree_hover)
        self.tree.bind("<Leave>", self.on_tree_leave)
        self.tree.bind("<Configure>", self.on_tree_resize)
        self.tree.bind("<MouseWheel>", self.on_mousewheel)
        self.tree.bind("<Button-4>", self.on_mousewheel)  # Linux scroll up
        self.tree.bind("<Button-5>", self.on_mousewheel)  # Linux scroll down
        btn_frame = tk.Frame(self)
        btn_frame.pack(side="bottom", fill="x")
        save_btn = ttk.Button(btn_frame, text="Save Changes", command=self.save_changes)
        save_btn.pack(side="right", pady=10, padx=10)
        close_btn = ttk.Button(btn_frame, text="Close Window", command=self.close_viewer)
        close_btn.pack(side="right", pady=10)

    def close_viewer(self):
        parent = self.master
        if isinstance(parent, tk.Tk):
            parent.destroy()
        elif isinstance(parent, tk.Toplevel):
            parent.destroy()
        else:
            self.destroy()

    def on_tree_resize(self, event):
        total_width = self.tree.winfo_width()
        include_width = self.tree.column("Include", option="width")
        type_width = self.tree.column("Type", option="width")
        scrollbar_width = 20
        remaining = max(0, total_width - include_width - type_width - scrollbar_width)
        from_to_width = max(80, remaining // 2)
        self.tree.column("From", width=from_to_width)
        self.tree.column("To", width=from_to_width)

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            rowid = self.tree.identify_row(event.y)
            col = self.tree.identify_column(event.x)
            if col == "#1" and rowid:
                idx = int(rowid)
                entry = self.planned_renames[idx]
                entry["include"] = 0 if entry["include"] else 1
                checked = "☑" if entry["include"] else "☐"
                self.tree.set(rowid, "Include", checked)

    def on_tree_hover(self, event):
        rowid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        # Track last tooltip cell to allow immediate update
        if not hasattr(self, '_last_tooltip_cell'):
            self._last_tooltip_cell = (None, None)
        if rowid and col:
            idx = int(rowid)
            entry = self.planned_renames[idx]
            col_map = {"#2": ("from", "From"), "#3": ("to", "To")}
            col_info = col_map.get(col)
            if col_info:
                col_name, col_id = col_info
                cell_val = get_relative_path(entry[col_name])
                col_width = self.tree.column(col_id, option="width")
                est_text_width = font.Font().measure(cell_val)
                if est_text_width > col_width:
                    x = self.tree.winfo_pointerx() + 20
                    y = self.tree.winfo_pointery() + 10
                    # Only update if cell or value changed, or tooltip not shown
                    if (rowid, col) != self._last_tooltip_cell or not self.tooltip or self.tooltip.text != cell_val:
                        if not self.tooltip:
                            self.tooltip = Tooltip(self.tree, cell_val)
                        else:
                            self.tooltip.text = cell_val
                            self.tooltip.hide()  # Hide before showing at new position
                        self.tooltip.show(x, y)
                        self._last_tooltip_cell = (rowid, col)
                    else:
                        # If tooltip is already shown for this cell, just update position
                        if self.tooltip:
                            self.tooltip.hide()
                            self.tooltip.show(x, y)
                else:
                    if self.tooltip:
                        self.tooltip.hide()
                        self.tooltip = None
                    self._last_tooltip_cell = (None, None)
            else:
                if self.tooltip:
                    self.tooltip.hide()
                    self.tooltip = None
                self._last_tooltip_cell = (None, None)
        else:
            if self.tooltip:
                self.tooltip.hide()
                self.tooltip = None
            self._last_tooltip_cell = (None, None)

    def on_tree_leave(self, event):
        if self.tooltip:
            self.tooltip.hide()
            self.tooltip = None
        self._last_tooltip_cell = (None, None)

    def on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.tree.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.tree.yview_scroll(1, "units")

    def save_changes(self):
        try:
            with open(PLANNED_RENAMES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.planned_renames, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Saved", "Changes saved to planned_renames.json")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
