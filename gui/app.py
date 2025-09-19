# gui/app.py
import tkinter as tk
from config import cfg, reload_config#, PREVIEW_FILE
from actions.omdb_gui_scraper import set_root
from undo import undo_last_operations
from pathlib import Path
import os
from actions.custom_imdb_web_poster_scraper import scrape_movie_posters, scrape_series_thumbnails, scrape_series_root_folders
from actions import movies, series
from gui.main_menu import MainMenu
from gui.preview_window import PreviewWindow, ExecuteWindow
from gui.undo_window import UndoWindow
from gui.scrape_window import ScrapeWindow
from gui.config_editor import ConfigEditorWindow

class AppRoot(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OMDb GUI Scraper")
        self.geometry("600x400")
        self.protocol("WM_DELETE_WINDOW", self.quit_app)

        self.canvas = tk.Canvas(self)
        self.v_scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set)

        self.v_scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.screen_container = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.screen_container, anchor="nw")
        self.screen_container.bind("<Configure>", self.on_frame_configure)

        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        self.show_main_menu()

    def on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def show_screen(self, screen_class, *args, **kwargs):
        for widget in self.screen_container.winfo_children():
            widget.destroy()
        screen = screen_class(self.screen_container, *args, **kwargs)
        screen.pack(fill="both", expand=True)
        return screen

    def show_main_menu(self):
        self.show_screen(
            MainMenu,
            show_preview=self.show_preview_window,
            show_execute=self.show_execute_window,
            show_undo=self.show_undo_window,
            show_scrape=self.show_scrape_window,
            show_config=self.show_config_editor_window,
            quit_app=self.quit_app
        )

    def show_preview_window(self):
        self.show_screen(PreviewWindow, on_back=self.show_main_menu)

    def show_execute_window(self):
        self.show_screen(ExecuteWindow, on_back=self.show_main_menu)

    def show_undo_window(self):
        self.show_screen(UndoWindow, on_back=self.show_main_menu)

    def show_scrape_window(self):
        self.show_screen(ScrapeWindow, on_back=self.show_main_menu)

    def show_config_editor_window(self):
        self.show_screen(ConfigEditorWindow, on_back=self.show_main_menu)

    def quit_app(self):
        self.destroy()
        os._exit(0)

def launch_app():
    root = AppRoot()
    set_root(root)
    root.mainloop()
