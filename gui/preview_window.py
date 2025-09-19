# gui/preview_window.py
import tkinter as tk
from gui.preview import generate_preview, execute_from_preview
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
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manual_series_mode.py")
        subprocess.run([sys.executable, script_path])
        # After completion, open batch edit window
        self.open_batch_edit()

    def do_generate(self):
        try:
            generate_preview()
            try:
                if self.status.winfo_exists():
                    self.status.config(text="Preview generated.")
                self.open_batch_edit()
                # self.open_planned_renames()
            except Exception:
                pass
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
