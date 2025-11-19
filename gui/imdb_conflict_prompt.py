import tkinter as tk
import threading
from io import BytesIO
import requests
from PIL import Image, ImageTk
from config import debug_print, ui_debug_print


def prompt_for_imdb_id_conflict(folder_name, conflicting_id, reason, master=None):
        """Show a small dialog asking the user to resolve an IMDb ID conflict.

        Returns:
        - None -> user chose Skip
        - str imdb_id -> user entered a different id (or clicked Use IMDb ID)
        - (imdb_id, True) -> user pressed "Use Same IMDb ID" override for this folder only

        This preserves the original prompt layout/behaviour but adds a poster image
        loaded (non-blocking) from the media cache entry for the conflicting_id, if available.
        """
    
        """Show a small dialog asking the user to resolve an IMDb ID conflict.

        Returns a manually entered IMDb ID string or None to indicate skip.
        """
        import tkinter as tk
        result = {'imdb_id': None, 'skip': False}
        def on_use():
            val = entry.get().strip()
            if val:
                result['imdb_id'] = val
                root.quit()
        def on_skip():
            result['skip'] = True
            root.quit()
        def on_overide():
            """Force-accept the conflicting IMDb ID for this folder only.

            This sets an 'override' flag so the caller can skip the usual
            "already used for another folder" check for this single decision.
            It does NOT persist the decision into imdb_cache, so other folders
            will still trigger the conflict dialog.
            """
            # Note: use the provided conflicting_id directly
            result['imdb_id'] = conflicting_id
            result['override'] = True
            root.quit()
        root = tk.Tk()
        root.title("IMDb ID Conflict")
        root.geometry("520x200")

        # Layout: left = details & entry, right = poster image (loaded async)
        content = tk.Frame(root)
        content.pack(fill='both', expand=True, padx=6, pady=6)

        left = tk.Frame(content)
        left.pack(side=tk.LEFT, fill='both', expand=True)

        tk.Label(left, text=f"Folder: {folder_name}", font=("Arial", 10, "bold")).pack(pady=2, anchor='w')
        tk.Label(left, text=f"Conflicting IMDb ID: {conflicting_id}", fg="red").pack(anchor='w')
        tk.Label(left, text=reason, wraplength=380, fg="darkred").pack(pady=4, anchor='w')
        entry = tk.Entry(left, width=40)
        entry.pack(pady=4)
        btn_frame = tk.Frame(left)
        btn_frame.pack(pady=4)
        use_btn = tk.Button(btn_frame, text="Use IMDb ID", command=on_use)
        use_btn.pack(side=tk.LEFT, padx=8)
        use_cache_btn = tk.Button(btn_frame, text="Use Existing Cache", command=lambda: on_use_cache())
        use_cache_btn.pack(side=tk.LEFT, padx=8)
        overide_btn = tk.Button(btn_frame, text="Use Same IMDb ID", command=on_overide)
        overide_btn.pack(side=tk.LEFT, padx=8)
        skip_btn = tk.Button(btn_frame, text="Skip Folder", command=on_skip)
        skip_btn.pack(side=tk.LEFT, padx=8)

        # Image frame on the right (placeholder until poster loads)
        img_frame = tk.Frame(content, width=140, height=180)
        img_frame.pack(side=tk.RIGHT, padx=(10, 10))
        img_frame.pack_propagate(False)
        img_label = tk.Label(img_frame, text="[No Image]", width=18, height=12)
        img_label.pack(fill='both', expand=True)

        # Try to load poster_url from media cache for conflicting_id and display it
        poster_url = None
        try:
            from core.media_metadata_cache import get_entry as _get_entry
            meta = _get_entry(conflicting_id)
            ui_debug_print(f"[DBG] imdb_conflict_prompt: media meta for {conflicting_id}: {repr(meta) if meta is not None else None}")
            poster_url = meta.get('poster_url') if meta else None
            ui_debug_print(f"[DBG] imdb_conflict_prompt: poster_url for {conflicting_id}: {poster_url}")
        except Exception as e:
            debug_print(f"[WARN] imdb_conflict_prompt: failed to read media cache for {conflicting_id}: {e}")
            poster_url = None

        # Callback to open an ExistingCachePicker and let the user pick an existing media cache entry
        def on_use_cache():
            try:
                ui_debug_print(f"[DBG] imdb_conflict_prompt: opening ExistingCachePicker for folder {folder_name}")
                from gui.existing_cache_picker import ExistingCachePickerFrame
                picker_done = tk.BooleanVar(root)
                selected = {'imdb_id': None}

                def picker_callback(imdb_id):
                    ui_debug_print(f"[DBG] imdb_conflict_prompt: cache picker returned imdb_id={imdb_id}")
                    selected['imdb_id'] = imdb_id
                    picker_done.set(True)

                top_cache = tk.Toplevel(root)
                top_cache.title("Pick Existing Cache Entry")
                top_cache.geometry("500x400+200+200")
                frame = ExistingCachePickerFrame(top_cache, folder_name, conflicting_id or '', picker_callback)
                frame.pack(fill='both', expand=True)
                top_cache.transient(root)
                top_cache.grab_set()
                root.wait_variable(picker_done)
                try:
                    top_cache.destroy()
                except Exception:
                    pass
                if selected['imdb_id']:
                    # Treat this as if the user entered that IMDb ID
                    result['imdb_id'] = selected['imdb_id']
                    picker_done.set(True)
                    root.quit()
            except Exception as e:
                debug_print(f"[WARN] imdb_conflict_prompt: failed to open cache picker: {e}")

        if poster_url:
            ui_debug_print(f"[DBG] imdb_conflict_prompt: starting poster download for {conflicting_id}: {poster_url}")
            def _set_img_from_bytes(img_bytes):
                try:
                    img = Image.open(BytesIO(img_bytes)).resize((140, 180))
                    img_tk = ImageTk.PhotoImage(img, master=root)
                    try:
                        img_label.configure(image=img_tk, text="")
                        setattr(img_label, "image", img_tk)
                        ui_debug_print(f"[DBG] imdb_conflict_prompt: poster set for {conflicting_id}")
                    except Exception as e:
                        debug_print(f"[WARN] imdb_conflict_prompt: failed to configure poster label for {conflicting_id}: {e}")
                except Exception as e:
                    debug_print(f"[WARN] imdb_conflict_prompt: failed to create PhotoImage for {conflicting_id}: {e}")

            def _download_and_schedule():
                try:
                    resp = requests.get(poster_url, timeout=6)
                    resp.raise_for_status()
                    data = resp.content
                    # schedule creation of PhotoImage in main thread
                    root.after(0, lambda d=data: _set_img_from_bytes(d))
                except Exception as e:
                    debug_print(f"[WARN] imdb_conflict_prompt: poster download failed for {conflicting_id}: {e}")

            t = threading.Thread(target=_download_and_schedule, daemon=True)
            t.start()

        entry.focus_set()
        root.mainloop()
        root.destroy()
        # Respect user choice: skip, override (return tuple), or entered id
        if result.get('skip'):
            return None
        if result.get('override'):
            # Return a tuple (imdb_id, override_flag) so callers can bypass
            # the "already used for another folder" conflict check for this
            # single prompt instance.
            return (result.get('imdb_id'), True)
        return result.get('imdb_id')
    
    
