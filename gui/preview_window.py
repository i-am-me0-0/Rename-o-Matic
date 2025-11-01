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
        btn_generate = tk.Button(self, text="Generate Preview", command=self.do_generate)
        btn_generate.pack(pady=5)
        btn_blank_slate = tk.Button(self, text="Create Blank Slate", command=self.blank_planned_renames)
        btn_blank_slate.pack(pady=5)
        btn_view_planned = tk.Button(self, text="View/Edit Planned Renames", command=self.open_planned_renames)
        btn_view_planned.pack(pady=5)
        btn_batch_edit = tk.Button(self, text="Batch Edit Planned Renames", command=self.open_batch_edit)
        btn_batch_edit.pack(pady=5)
        btn_back = tk.Button(self, text="Back", command=on_back)
        btn_back.pack(pady=10)
        self.status = tk.Label(self, text="")
        self.status.pack(pady=5)

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
