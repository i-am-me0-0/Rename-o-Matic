
# gui/episode_id_prompt.py
import tkinter as tk
from tkinter import messagebox
import re

def prompt_for_episode_id(show_name, prompt_msg):
    """
    Simple blocking prompt for a single IMDb episode ID (for edge/specials).
    Returns the entered IMDb episode ID (or None if cancelled).
    """
    root = tk.Tk()
    root.withdraw()
    result = None
    def on_submit():
        nonlocal result
        val = entry.get().strip()
        match = re.search(r'(tt\d{7,})', val)
        result = match.group(1) if match else val
        win.destroy()
        root.quit()
    def on_cancel():
        nonlocal result
        result = None
        win.destroy()
        root.quit()
    win = tk.Toplevel(root)
    win.title(f"Enter IMDb Episode ID: {show_name}")
    win.geometry("600x180")  # Make window wider
    label = tk.Label(win, text=prompt_msg, font=("Arial", 12))
    label.pack(pady=10)
    entry = tk.Entry(win, width=48)  # Make input box wider
    entry.pack(pady=10)
    entry.focus_set()
    btn_frame = tk.Frame(win)
    btn_frame.pack(pady=10)
    btn_ok = tk.Button(btn_frame, text="OK", command=on_submit)
    btn_ok.pack(side="left", padx=5)
    btn_cancel = tk.Button(btn_frame, text="Cancel", command=on_cancel)
    btn_cancel.pack(side="left", padx=5)
    win.protocol("WM_DELETE_WINDOW", on_cancel)
    win.grab_set()
    root.mainloop()
    root.destroy()
    return result

class EpisodeIDPrompt(tk.Toplevel):
    def __init__(self, master, show_name, missing_episodes, on_submit, file_names=None):
        super().__init__(master)
        self.title(f"Enter IMDb IDs for Missing Episodes: {show_name}")
        self.entries = {}
        self.on_submit = on_submit
        self.result = {}
        self.geometry("1010x500")  # Make window wider
        label = tk.Label(self, text=f"Enter IMDb ID for each missing episode of {show_name} (leave blank or click Skip to leave empty):", font=("Arial", 12))
        label.pack(pady=5)
        label2 = tk.Label(self, text=f"An IMDb url is also accepted", font=("Arial", 10))
        label2.pack(pady=2)
        # Add a scrollable frame
        canvas = tk.Canvas(self)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)
        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for i, ep in enumerate(missing_episodes):
            row = tk.Frame(scroll_frame)
            row.pack(fill="x", pady=2)
            ep_label = ep
            if file_names and i < len(file_names):
                ep_label += f" | File: {file_names[i]}"
            lbl = tk.Label(row, text=ep_label, width=80, anchor="w")  # Wider label
            lbl.pack(side="left")
            entry = tk.Entry(row, width=50)  # Wider entry box
            entry.pack(side="left")
            # Bind to <KeyRelease> so the entry auto-scrolls to the end as you type
            def autoscroll(event, e=entry):
                e.xview_moveto(1)
            entry.bind('<KeyRelease>', autoscroll)
            self.entries[ep] = entry
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        btn_submit = tk.Button(btn_frame, text="Submit", command=self.submit)
        btn_submit.pack(side="left", padx=5)
        btn_skip = tk.Button(btn_frame, text="Skip All", command=self.skip_all)
        btn_skip.pack(side="left", padx=5)
        self.protocol("WM_DELETE_WINDOW", self.skip_all)
    def submit(self):
        for ep, entry in self.entries.items():
            imdb_id = entry.get().strip()
            # Extract tt####### from full IMDb URL if present
            match = re.search(r'(tt\d{7,})', imdb_id)
            imdb_id = match.group(1) if match else imdb_id
            self.result[ep] = imdb_id
        self.on_submit(self.result)
        self.destroy()
    def skip_all(self):
        for ep in self.entries:
            self.result[ep] = ""
        self.on_submit(self.result)
        self.destroy()
