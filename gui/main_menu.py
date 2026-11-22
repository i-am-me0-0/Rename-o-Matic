# gui/main_menu.py
import tkinter as tk

class MainMenu(tk.Frame):
    def __init__(self, master, show_preview, show_execute, show_undo, show_scrape, show_config, quit_app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        label = tk.Label(self, text="Welcome to Rename-o-Matic!", font=("Arial", 16))
        label.pack(pady=20)

        btn_preview = tk.Button(self, text="Generate Preview", command=show_preview)
        btn_preview.pack(pady=10)

        btn_execute = tk.Button(self, text="Execute from Preview", command=show_execute)
        btn_execute.pack(pady=10)

        btn_undo = tk.Button(self, text="Undo Last Operations", command=show_undo)
        btn_undo.pack(pady=10)

        btn_scrape = tk.Button(self, text="Scrape Images", command=show_scrape)
        btn_scrape.pack(pady=10)

        btn_config = tk.Button(self, text="Edit Configuration", command=show_config)
        btn_config.pack(pady=10)

        btn_close = tk.Button(self, text="Close", command=quit_app)
        btn_close.pack(pady=10)
