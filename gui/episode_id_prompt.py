
# gui/episode_id_prompt.py
import tkinter as tk
import re
from typing import Callable, Any, List, Optional

try:
    # Try to import get_root so frame-based prompts can use AppRoot
    from actions.omdb_gui_scraper import get_root
except Exception:
    get_root = None


def prompt_for_episode_id(show_name: str, prompt_msg: str) -> Optional[str]:
    """
    Blocking prompt for a single IMDb episode ID.
    If running inside the AppRoot, uses a frame-based prompt via show_screen.
    Otherwise falls back to a Toplevel modal.
    """
    # Try frame-based flow via AppRoot
    try:
        if get_root:
            app_root = get_root()
            done_var = tk.BooleanVar(app_root)
            # use a distinct dict name so the fallback flow (which uses `result = None`)
            # doesn't make the typechecker assume this variable can be None or a str.
            # initialize with string-typed default so __setitem__ accepts str
            result_container = {'id': ''}

            def _on_submit(val: Optional[str]):
                # coerce None to empty string so the stored value is always str
                result_container['id'] = val or ''
                done_var.set(True)

            app_root.show_screen(EpisodeIDPromptFrame, show_name, prompt_msg, _on_submit)
            app_root.wait_variable(done_var)
            return result_container['id']
    except Exception:
        pass

    # Fallback: Toplevel modal (CLI/standalone mode)
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
    win.geometry("600x180")
    label = tk.Label(win, text=prompt_msg, font=("Arial", 12))
    label.pack(pady=10)
    entry = tk.Entry(win, width=48)
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


class EpisodeIDPromptFrame(tk.Frame):
    """Frame-based prompt for a single IMDb episode ID (used inside AppRoot)."""
    def __init__(self, master: Any, show_name: str, prompt_msg: str, on_submit: Callable[[Optional[str]], None]):
        super().__init__(master)
        self.on_submit = on_submit
        tk.Label(self, text=prompt_msg, font=("Arial", 12)).pack(pady=10)
        self.entry = tk.Entry(self, width=48)
        self.entry.pack(pady=8)
        self.entry.focus_set()
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=8)
        tk.Button(btn_frame, text="OK", command=self._ok).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side="left", padx=5)

    def _ok(self):
        val = self.entry.get().strip()
        match = re.search(r'(tt\d{7,})', val)
        val = match.group(1) if match else val
        try:
            self.on_submit(val)
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _cancel(self):
        try:
            self.on_submit(None)
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


class EpisodeIDPrompt(tk.Toplevel):
    """Compatibility Toplevel used by non-GUI flows; kept for backward compatibility."""
    def __init__(self, master, show_name, missing_episodes: List[str], on_submit: Callable[[dict], None], file_names=None):
        super().__init__(master)
        self.title(f"Enter IMDb IDs for Missing Episodes: {show_name}")
        self.entries = {}
        self.on_submit = on_submit
        self.result = {}
        self.geometry("1010x500")
        label = tk.Label(self, text=f"Enter IMDb ID for each missing episode of {show_name} (leave blank or click Skip to leave empty):", font=("Arial", 12))
        label.pack(pady=5)
        label2 = tk.Label(self, text=f"An IMDb url is also accepted", font=("Arial", 10))
        label2.pack(pady=2)
        label3 = tk.Label(
            self,
            text="Tip: For double-episode rows, use both fields (or paste both IMDb IDs/URLs in the first field).",
            font=("Arial", 10)
        )
        label3.pack(pady=2)
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

        def _is_double_episode_label(label_text: str) -> bool:
            try:
                return bool(re.search(r"\bS\d{1,2}E\d{1,2}(?:-E\d{1,2})+\b", label_text or "", flags=re.I))
            except Exception:
                return False

        for i, ep in enumerate(missing_episodes):
            row = tk.Frame(scroll_frame)
            row.pack(fill="x", pady=2)
            ep_label = ep
            if file_names and i < len(file_names):
                ep_label += f" | File: {file_names[i]}"
            lbl = tk.Label(row, text=ep_label, width=80, anchor="w")
            lbl.pack(side="left")

            if _is_double_episode_label(ep):
                entry1 = tk.Entry(row, width=24)
                entry1.pack(side="left", padx=(0, 4))
                sep_lbl = tk.Label(row, text="|")
                sep_lbl.pack(side="left", padx=2)
                entry2 = tk.Entry(row, width=24)
                entry2.pack(side="left", padx=(4, 0))

                def autoscroll_dual_1(event, e=entry1):
                    e.xview_moveto(1)

                def autoscroll_dual_2(event, e=entry2):
                    e.xview_moveto(1)

                entry1.bind('<KeyRelease>', autoscroll_dual_1)
                entry2.bind('<KeyRelease>', autoscroll_dual_2)
                self.entries[ep] = (entry1, entry2)
            else:
                entry = tk.Entry(row, width=50)
                entry.pack(side="left")

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
            raw_value = ""
            if isinstance(entry, tuple):
                left = entry[0].get().strip() if entry[0] else ""
                right = entry[1].get().strip() if entry[1] else ""
                if left and right:
                    raw_value = f"{left} | {right}"
                else:
                    raw_value = left or right
            else:
                raw_value = entry.get().strip()

            matches = re.findall(r'(tt\d{7,})', raw_value)
            if len(matches) > 1:
                # Preserve both/all IDs so dual-episode handlers can map one per episode.
                imdb_value = "|".join(matches)
            elif len(matches) == 1:
                imdb_value = matches[0]
            else:
                if isinstance(entry, tuple):
                    left = entry[0].get().strip() if entry[0] else ""
                    right = entry[1].get().strip() if entry[1] else ""
                    if left and right:
                        imdb_value = f"{left}|{right}"
                    else:
                        imdb_value = left or right
                else:
                    imdb_value = raw_value
            self.result[ep] = imdb_value
        try:
            self.on_submit(self.result)
        except Exception:
            pass
        self.destroy()

    def skip_all(self):
        for ep in self.entries:
            self.result[ep] = ""
        try:
            self.on_submit(self.result)
        except Exception:
            pass
        self.destroy()
