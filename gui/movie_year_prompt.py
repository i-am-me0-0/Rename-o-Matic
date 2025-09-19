# gui/movie_year_prompt.py
import tkinter as tk
from tkinter import simpledialog, messagebox

class MovieYearPrompt(tk.Toplevel):
    def __init__(self, master, movies_missing_year, on_submit):
        super().__init__(master)
        self.title("Enter Missing Years for Movies")
        self.entries = {}
        self.on_submit = on_submit
        self.result = {}
        self.geometry("500x400")
        label = tk.Label(self, text="Enter the year for each movie (leave blank or click Skip to use 0000):", font=("Arial", 12))
        label.pack(pady=10)
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True)
        for movie in movies_missing_year:
            row = tk.Frame(frame)
            row.pack(fill="x", pady=2)
            lbl = tk.Label(row, text=movie, width=40, anchor="w")
            lbl.pack(side="left")
            entry = tk.Entry(row, width=8)
            entry.pack(side="left")
            self.entries[movie] = entry
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        btn_submit = tk.Button(btn_frame, text="Submit", command=self.submit)
        btn_submit.pack(side="left", padx=5)
        btn_skip = tk.Button(btn_frame, text="Skip All", command=self.skip_all)
        btn_skip.pack(side="left", padx=5)
        self.protocol("WM_DELETE_WINDOW", self.skip_all)
    def submit(self):
        for movie, entry in self.entries.items():
            year = entry.get().strip()
            if not year:
                year = "0000"
            self.result[movie] = year
        self.on_submit(self.result)
        self.destroy()
    def skip_all(self):
        for movie in self.entries:
            self.result[movie] = "0000"
        self.on_submit(self.result)
        self.destroy()
