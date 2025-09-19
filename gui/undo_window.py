# gui/undo_window.py
import tkinter as tk
from undo import undo_last_operations

class UndoWindow(tk.Frame):
    def __init__(self, master, on_back, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        label = tk.Label(self, text="Undo Last Operations", font=("Arial", 14))
        label.pack(pady=10)
        btn_undo = tk.Button(self, text="Undo", command=self.do_undo)
        btn_undo.pack(pady=5)
        btn_back = tk.Button(self, text="Back", command=on_back)
        btn_back.pack(pady=10)
        self.status = tk.Label(self, text="")
        self.status.pack(pady=5)

    def do_undo(self):
        try:
            undo_last_operations()
            self.status.config(text="Undo complete.")
        except Exception as e:
            self.status.config(text=f"Error: {e}")
