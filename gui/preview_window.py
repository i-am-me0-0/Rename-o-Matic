# gui/preview_window.py
import os
import tkinter as tk
from actions.preview import generate_preview, execute_from_preview
from config import debug_print
from gui.planned_renames_viewer import PlannedRenamesFrame

class PreviewWindow(tk.Frame):
    def __init__(self, master, on_back, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        label = tk.Label(self, text="Generate Preview", font=("Arial", 14))
        label.pack(pady=10)
        
        # Container for two columns
        columns_frame = tk.Frame(self)
        columns_frame.pack(pady=10)
        
        # Left column
        left_column = tk.Frame(columns_frame)
        left_column.pack(side="left", padx=10)
        
        btn_generate = tk.Button(left_column, text="Generate Preview", command=self.do_generate)
        btn_generate.pack(pady=5)
        btn_blank_slate = tk.Button(left_column, text="Create Blank Slate", command=self.blank_planned_renames)
        btn_blank_slate.pack(pady=5)
        btn_blank_slate = tk.Button(left_column, text="Manual TVDB Scraper", command=self.manual_series_tvdb_scraper)
        btn_blank_slate.pack(pady=5)
        btn_view_planned = tk.Button(left_column, text="View/Edit Planned Renames", command=self.open_planned_renames)
        btn_view_planned.pack(pady=5)
        btn_batch_edit = tk.Button(left_column, text="Batch Edit Planned Renames", command=self.open_batch_edit)
        btn_batch_edit.pack(pady=5)
        
        # Divider line
        divider = tk.Frame(columns_frame, width=2, bg="gray")
        divider.pack(side="left", fill="y", padx=10)
        
        # Right column
        right_column = tk.Frame(columns_frame)
        right_column.pack(side="left", padx=10)
        
        btn_preview_cache = tk.Button(right_column, text="Preview Metadata Cache", command=self.open_cache_preview)
        btn_preview_cache.pack(pady=5)
        btn_omdb_scraper = tk.Button(right_column, text="OMDB Scraper", command=self.open_omdb_scraper)
        btn_omdb_scraper.pack(pady=5)
        btn_season_remap = tk.Button(right_column, text="Season Episode Remap", command=self.open_season_episode_remap)
        btn_season_remap.pack(pady=5)
        
        # Usage stats at bottom of right column
        self.usage_label = tk.Label(right_column, text="", font=("Arial", 9), fg="gray")
        self.usage_label.pack(pady=(20, 5))
        self.update_usage_stats()
        
        btn_back = tk.Button(self, text="Back", command=on_back)
        btn_back.pack(pady=10)
        self.status = tk.Label(self, text="")
        self.status.pack(pady=5)
    
    def update_usage_stats(self):
        """Update the usage statistics display."""
        try:
            from actions.omdb_gui_scraper import get_usage_stats
            from config import OMDB_API_KEY
            stats = get_usage_stats(OMDB_API_KEY)
            self.usage_label.config(text=f"Usage: {stats['key_label']}: {stats['today']}/{stats['limit']}")
        except Exception:
            self.usage_label.config(text="")

    def open_planned_renames(self):
        win = tk.Toplevel(self)
        win.title("Planned Renames")
        frame = PlannedRenamesFrame(win)
        frame.pack(fill="both", expand=True)
        win.geometry("1200x800")

    def open_batch_edit(self):
        from gui.batch_edit_planned_renames import BatchEditPlannedRenames 
        win = tk.Toplevel(self)
        win.title("Batch Edit Planned Renames")
        frame = BatchEditPlannedRenames(win)
        frame.pack(fill="both", expand=True)
        win.geometry("1400x900")

    def open_cache_preview(self):
        """Open cache picker to browse all cached metadata."""
        from gui.existing_cache_picker import ExistingCachePickerFrame
        win = tk.Toplevel(self)
        win.title("Preview Metadata Cache")
        
        def on_selection(selected_id):
            """Handle selection from cache preview."""
            if selected_id:
                # Just close the window - this is preview only
                try:
                    win.destroy()
                except Exception:
                    pass
        
        # Create the picker frame with empty name to show all entries
        frame = ExistingCachePickerFrame(
            win, 
            name="",  # Empty name shows all entries
            conflicting_id="",  # No conflict
            on_choice=on_selection,
            filter_type=None  # Show both movies and series
        )
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        win.geometry("832x530")

    def open_omdb_scraper(self):
        """Open OMDB scraper window for manual metadata lookup."""
        from gui.omdb_scraper_window import OMDBScraperWindow
        win = tk.Toplevel(self)
        win.title("OMDB Scraper")
        frame = OMDBScraperWindow(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        win.geometry("700x500")

    def open_season_episode_remap(self):
        """Open season remap tool to correct OMDb season indexing into manual cache."""
        from gui.season_episode_remap_window import SeasonEpisodeRemapWindow
        win = tk.Toplevel(self)
        win.title("Season Episode Remap")
        frame = SeasonEpisodeRemapWindow(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        win.geometry("1200x760")

    def blank_planned_renames(self):
        import subprocess
        import sys
        import os
        # Run manual_series_mode.py to generate blank planned renames
        # script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manual_series_mode.py")
        # subprocess.run([sys.executable, script_path])
        from actions.manual_series_mode import main
        main()
        # After completion, open batch edit window
        self.open_batch_edit()

    def manual_series_tvdb_scraper(self):
        import subprocess
        import sys
        import os
        # Run manual_series_mode.py to generate blank planned renames
        # script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manual_series_mode.py")
        # subprocess.run([sys.executable, script_path])
        from actions.manual_series_tvdb_scraper import main
        main()
        # After completion, open batch edit window
        self.open_batch_edit()

        

    def do_generate(self):
        debug_print("[DEBUG] PreviewWindow.do_generate: started")
        try:
            # Prefer running generate_preview with the AppRoot so prompts use frame-based flows
            try:
                from actions.omdb_gui_scraper import get_root
                #debug_print("[DEBUG] PreviewWindow.do_generate: get_root() found; calling generate_preview with app root")
                try:
                    generate_preview(get_root())
                    #debug_print("[DEBUG] PreviewWindow.do_generate: generate_preview returned (root path)")
                except Exception as e:
                    debug_print(f"[DEBUG] PreviewWindow.do_generate: generate_preview(root) failed: {e}; falling back to generate_preview()")
                    # fallback to non-root generate
                    generate_preview()
            except Exception:
                debug_print("[DEBUG] PreviewWindow.do_generate: get_root() unavailable; calling generate_preview()")
                # If get_root isn't available, run CLI-style preview
                generate_preview()

            if self.status.winfo_exists():
                self.status.config(text="Preview generated.")
            debug_print("[DEBUG] PreviewWindow.do_generate: preview generated; attempting to re-show preview frame and open batch edit")

            # Re-show the PreviewWindow in the main container (it may have been replaced
            # by frame-based prompts during generation) so the main container is not left empty,
            # then open the Batch Edit window on top.
            try:
                from actions.omdb_gui_scraper import get_root
                #debug_print("[DEBUG] PreviewWindow.do_generate: attempting to re-create PreviewWindow in main container")
                app_root = get_root()
                # Use app_root.show_main_menu as the on_back target to avoid passing a bound
                # method from the possibly destroyed previous PreviewWindow instance.
                preview_frame = app_root.show_screen(PreviewWindow, on_back=app_root.show_main_menu)
                debug_print(f"[DEBUG] PreviewWindow.do_generate: preview_frame created: {preview_frame}")
                try:
                    debug_print("[DEBUG] PreviewWindow.do_generate: opening batch edit from preview_frame")
                    preview_frame.open_batch_edit()
                    debug_print("[DEBUG] PreviewWindow.do_generate: batch edit opened")
                except Exception as e:
                    debug_print(f"[DEBUG] PreviewWindow.do_generate: preview_frame.open_batch_edit() failed: {e}; falling back to self.open_batch_edit()")
                    # fallback to current instance
                    try:
                        self.open_batch_edit()
                        debug_print("[DEBUG] PreviewWindow.do_generate: fallback self.open_batch_edit() succeeded")
                    except Exception as e2:
                        debug_print(f"[ERROR] PreviewWindow.do_generate: fallback self.open_batch_edit() failed: {e2}")

                # --- Run test_planned_renames.py function if TEST env var is set ---
                if os.environ.get("RENAMER_TEST_MODE") == "1":
                    debug_print("[DEBUG] PreviewWindow.do_generate: RENAMER_TEST env detected, running test_planned_renames.run_test()")
                    try:
                        from test_planned_renames import run_test
                        run_test()
                    except Exception as e:
                        debug_print(f"[ERROR] PreviewWindow.do_generate: test_planned_renames.run_test() failed: {e}")

            except Exception as e:
                debug_print(f"[DEBUG] PreviewWindow.do_generate: failed to re-create preview frame or open batch edit: {e}; attempting fallback open_batch_edit() on current frame")
                # fallback behavior: open batch edit on current frame
                try:
                    self.open_batch_edit()
                    debug_print("[DEBUG] PreviewWindow.do_generate: fallback open_batch_edit() succeeded")
                except Exception as e3:
                    debug_print(f"[ERROR] PreviewWindow.do_generate: fallback open_batch_edit() failed: {e3}")

        except Exception as e:
            try:
                if self.status.winfo_exists():
                    self.status.config(text=f"Error: {e}")
            except Exception:
                pass

class ExecuteWindow(tk.Frame):
    def __init__(self, master, on_back, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        label = tk.Label(self, text="Execute from Preview", font=("Arial", 14))
        label.pack(pady=10)
        btn_execute = tk.Button(self, text="Execute Renames", command=self.do_execute)
        btn_execute.pack(pady=5)
        btn_back = tk.Button(self, text="Back", command=on_back)
        btn_back.pack(pady=10)
        self.status = tk.Label(self, text="")
        self.status.pack(pady=5)

    def do_execute(self):
        try:
            execute_from_preview()
            try:
                if self.status.winfo_exists():
                    self.status.config(text="Execution complete.")
            except Exception:
                pass
        except Exception as e:
            try:
                if self.status.winfo_exists():
                    self.status.config(text=f"Error: {e}")
            except Exception:
                pass
