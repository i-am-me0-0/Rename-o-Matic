import tkinter as tk
from typing import Any, Callable, List, Tuple, Optional
import threading
from io import BytesIO
try:
    import requests
    from PIL import Image, ImageTk
except Exception:
    requests = None
    Image = None

from core.media_metadata_cache import load_metadata
from core.manual_episode_cache import load_manual_episode_cache


class ExistingCachePickerFrame(tk.Frame):
    """Frame that lets the user pick an existing media-cache entry to reuse.

    The frame will search the local media metadata cache for titles matching
    the provided folder/show name and present a list with small poster thumbnails.
    """
    def __init__(self, master: Any, name: str, conflicting_id: str, on_choice: Callable[[Optional[str]], None], filter_type: Optional[str] = None):
        super().__init__(master)
        self.on_choice = on_choice
        self._poster_img = None
        # Monotonic token used to ignore stale async poster callbacks.
        self._poster_request_token = 0
        self.matches: List[Tuple[str, str, dict]] = []  # (label, imdb_id, meta)
        self.name = name
        self.conflicting_id = conflicting_id  # Store for later use
        self.filter_type = filter_type.lower() if filter_type else None

        top = tk.Frame(self)
        top.pack(fill='both', expand=True, padx=8, pady=6)

        left = tk.Frame(top)
        left.pack(side='left', fill='y', padx=(0,8))

        # Fixed size container for images to prevent layout shifts
        img_container = tk.Frame(left, width=240, height=200)
        img_container.pack()
        img_container.pack_propagate(False)  # Prevent frame from resizing to contents
        
        self.img_label = tk.Label(img_container, text="[No Image]")
        self.img_label.place(relx=0.5, rely=0.5, anchor='center')  # Center in container

        # Info display area for metadata
        info_frame = tk.Frame(left, relief='sunken', borderwidth=1)
        info_frame.pack(fill='both', expand=True, pady=(8,0))
        
        self.info_text = tk.Text(info_frame, wrap='word', height=10, width=20, font=('Arial', 9))
        self.info_text.pack(side='left', fill='both', expand=True)
        info_scrollbar = tk.Scrollbar(info_frame, command=self.info_text.yview)
        info_scrollbar.pack(side='right', fill='y')
        self.info_text.config(yscrollcommand=info_scrollbar.set, state='disabled')

        right = tk.Frame(top)
        right.pack(side='left', fill='both', expand=True)

        display_name = name if name else '(Unknown)'
        tk.Label(right, text=f"File: {display_name}", font=("Arial", 11, "bold")).pack(anchor='w')

        # Search filter box
        search_frame = tk.Frame(right)
        search_frame.pack(fill='x', pady=(6,0))
        tk.Label(search_frame, text="Filter:").pack(side='left', padx=(0,4))
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self._filter_listbox())
        search_entry = tk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side='left', fill='x', expand=True, padx=(0,4))
        
        # Filter checkboxes frame
        filter_checks_frame = tk.Frame(right)
        filter_checks_frame.pack(fill='x', pady=(4,0))
        
        # Checkbox to filter for entries with images
        self.images_only_var = tk.BooleanVar(value=False)
        tk.Checkbutton(filter_checks_frame, text="📷 Only", variable=self.images_only_var, command=self._filter_listbox).pack(side='left', padx=(0,4))
        
        # Checkbox to filter for entries with NO images
        self.no_images_var = tk.BooleanVar(value=False)
        tk.Checkbutton(filter_checks_frame, text="No 📷", variable=self.no_images_var, command=self._filter_listbox).pack(side='left', padx=(0,4))
        
        # Checkbox to show only orphaned episodes
        self.orphaned_only_var = tk.BooleanVar(value=False)
        tk.Checkbutton(filter_checks_frame, text="Orphaned", variable=self.orphaned_only_var, command=self._filter_listbox).pack(side='left', padx=(0,4))
        
        # Checkbox to hide episodes
        self.hide_episodes_var = tk.BooleanVar(value=False)
        tk.Checkbutton(filter_checks_frame, text="Hide Episodes", variable=self.hide_episodes_var, command=self._filter_listbox).pack(side='left', padx=(0,4))

        # Listbox with scrollbar
        list_frame = tk.Frame(right)
        list_frame.pack(fill='both', expand=True, pady=(6,0))
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')
        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, selectmode=tk.SINGLE)
        self.listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.listbox.yview)

        # Buttons
        btnf = tk.Frame(self)
        btnf.pack(pady=8)
        tk.Button(btnf, text="Use Selected", width=14, command=self._use_selected).pack(side='left', padx=6)
        tk.Button(btnf, text="Refresh from OMDB", width=16, command=self._refresh_from_omdb).pack(side='left', padx=6)
        tk.Button(btnf, text="Repair Series Episodes", width=18, command=self._repair_series_episodes).pack(side='left', padx=6)
        tk.Button(btnf, text="Enter ID Manually", width=16, command=self._prompt_manual).pack(side='left', padx=6)
        tk.Button(btnf, text="Rescrape New ID", width=16, command=self._rescrape).pack(side='left', padx=6)
        tk.Button(btnf, text="Use Original ID", width=16, command=self._use_original).pack(side='left', padx=6)

        # Populate matches in background
        self._load_matches_async(name)

        # When selection changes, show poster
        self.listbox.bind('<<ListboxSelect>>', lambda e: self._on_select())

    def _normalize(self, s: str) -> str:
        try:
            import re, unicodedata
            s2 = unicodedata.normalize('NFKD', str(s) or '')
            s2 = re.sub(r"[^\n\w\s]", ' ', s2).lower()
            s2 = re.sub(r"\s+", ' ', s2).strip()
            return s2
        except Exception:
            return (s or '').lower().strip()

    def _is_orphaned_episode(self, episode_id: str, cache_data: dict) -> bool:
        """Check if an episode is not linked to any series."""
        try:
            # Check in media metadata cache (episodes dict in series)
            for series_id, series_meta in cache_data.items():
                if series_meta.get('type', '').lower() == 'series':
                    episodes_dict = series_meta.get('episodes', {})
                    if episodes_dict and isinstance(episodes_dict, dict):
                        for season_eps in episodes_dict.values():
                            if isinstance(season_eps, dict) and episode_id in season_eps.values():
                                return False  # Found in a series
            
            # Also check manual episode cache
            try:
                manual_cache = load_manual_episode_cache()
                for series_id, series_seasons in manual_cache.items():
                    if isinstance(series_seasons, dict):
                        for season_eps in series_seasons.values():
                            if isinstance(season_eps, dict) and episode_id in season_eps.values():
                                return False  # Found in manual cache
            except Exception:
                pass  # If manual cache can't be loaded, continue
            
            return True  # Not found in any series
        except Exception:
            return False  # Default to not orphaned if error occurs

    def _load_matches_async(self, name: str):
        def _worker():
            try:
                needle = self._normalize(name or '')
                data = load_metadata()
                def type_matches(meta_type):
                    if not self.filter_type:
                        return True
                    if not meta_type:
                        return False
                    return str(meta_type).strip().lower() == self.filter_type

                # 1. Try strict match (needle in normalized title)
                for mid, meta in data.items():
                    if not type_matches(meta.get('type')):
                        continue
                    title = (meta.get('title') or '')
                    if not title:
                        continue
                    if needle and needle in self._normalize(title):
                        year = meta.get('year') or meta.get('end_year') or ''
                        media_type = meta.get('type', '').capitalize()
                        # Add image indicator if poster exists
                        img_indicator = '📷 ' if meta.get('poster_url') else ''
                        # Check if episode is orphaned
                        orphaned_tag = ' (Orphaned)' if media_type.lower() == 'episode' and self._is_orphaned_episode(mid, data) else ''
                        label = f"{img_indicator}{title} ({year}) [{mid}] ({media_type}){orphaned_tag}"
                        self.matches.append((label, mid, meta))

                # 2. If nothing found, try looser match: substring of folder words
                if not self.matches and name:
                    parts = [p for p in name.split() if len(p) > 3]
                    for mid, meta in data.items():
                        if not type_matches(meta.get('type')):
                            continue
                        title = (meta.get('title') or '')
                        if not title:
                            continue
                        norm = self._normalize(title)
                        if any(self._normalize(p) in norm for p in parts):
                            year = meta.get('year') or meta.get('end_year') or ''
                            media_type = meta.get('type', '').capitalize()
                            # Add image indicator if poster exists
                            img_indicator = '📷 ' if meta.get('poster_url') else ''
                            # Check if episode is orphaned
                            orphaned_tag = ' (Orphaned)' if media_type.lower() == 'episode' and self._is_orphaned_episode(mid, data) else ''
                            label = f"{img_indicator}{title} ({year}) [{mid}] ({media_type}){orphaned_tag}"
                            self.matches.append((label, mid, meta))

                # 3. If still nothing, show all entries of the correct type
                if not self.matches:
                    for mid, meta in data.items():
                        if not type_matches(meta.get('type')):
                            continue
                        title = (meta.get('title') or '')
                        if not title:
                            continue
                        year = meta.get('year') or meta.get('end_year') or ''
                        media_type = meta.get('type', '').capitalize()
                        # Add image indicator if poster exists
                        img_indicator = '📷 ' if meta.get('poster_url') else ''
                        # Check if episode is orphaned
                        orphaned_tag = ' (Orphaned)' if media_type.lower() == 'episode' and self._is_orphaned_episode(mid, data) else ''
                        label = f"{img_indicator}{title} ({year}) [{mid}] ({media_type}){orphaned_tag}"
                        self.matches.append((label, mid, meta))
            except Exception:
                pass
            # update UI on main thread
            try:
                self.after(0, self._populate_listbox)
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _populate_listbox(self):
        self.listbox.delete(0, tk.END)
        for lbl, mid, meta in self.matches:
            self.listbox.insert(tk.END, lbl)
    
    def _filter_listbox(self):
        """Filter the listbox based on search text and filter checkboxes."""
        search_text = self.search_var.get().lower()
        images_only = self.images_only_var.get()
        no_images = self.no_images_var.get()
        orphaned_only = self.orphaned_only_var.get()
        hide_episodes = self.hide_episodes_var.get()
        
        self.listbox.delete(0, tk.END)
        
        for lbl, mid, meta in self.matches:
            # Check text filter
            if search_text and search_text not in lbl.lower():
                continue
            
            # Check image filters (mutually exclusive)
            has_poster = bool(meta.get('poster_url'))
            if images_only and not has_poster:
                continue
            if no_images and has_poster:
                continue
            
            # Check episode type filters
            is_episode = meta.get('type', '').lower() == 'episode'
            
            # Hide episodes filter
            if hide_episodes and is_episode:
                continue
            
            # Orphaned only filter - only show if it's an orphaned episode
            if orphaned_only:
                if not is_episode:
                    continue  # Not an episode, skip
                if '(Orphaned)' not in lbl:
                    continue  # Not orphaned, skip
            
            self.listbox.insert(tk.END, lbl)

    def _update_info_display(self, meta: dict, mid: Optional[str] = None):
        """Update the info text widget with metadata details."""
        self.info_text.config(state='normal')
        self.info_text.delete('1.0', tk.END)
        
        if not meta:
            self.info_text.config(state='disabled')
            return
        
        info_lines = []
        
        # Show title
        title = meta.get('title', '')
        if title:
            info_lines.append(f"Title: {title}\n")
        
        # Show year
        year = meta.get('year', '')
        if year:
            info_lines.append(f"Year: {year}\n")
        
        # Show type
        media_type = meta.get('type', '').capitalize()
        if media_type:
            info_lines.append(f"Type: {media_type}\n")
        
        # Show IMDb ID
        if mid:
            info_lines.append(f"IMDb ID: {mid}\n")
        
        # Show release date if available (for all types)
        released = meta.get('released', '')
        if released:
            info_lines.append(f"Released: {released}\n")
        
        # For episodes, find and show parent series
        if meta.get('type', '').lower() == 'episode' and mid:
            
            found_parent = False
            try:
                # Search for parent series in cache
                cache_data = load_metadata()
                for series_id, series_meta in cache_data.items():
                    if found_parent:
                        break
                    if series_meta.get('type', '').lower() == 'series':
                        episodes_dict = series_meta.get('episodes', {})
                        if not episodes_dict or not isinstance(episodes_dict, dict):
                            continue
                        # Check if this episode is in any season
                        for season_num, season_eps in episodes_dict.items():
                            if not isinstance(season_eps, dict):
                                continue
                            # Check if episode ID is in this season's episodes
                            if mid in season_eps.values():
                                series_title = series_meta.get('title', '')
                                if series_title:
                                    info_lines.append(f"\nSeries: {series_title}\n")
                                    # Find episode number
                                    for ep_num, ep_id in season_eps.items():
                                        if ep_id == mid:
                                            info_lines.append(f"Season {season_num}, Episode {ep_num}\n")
                                            found_parent = True
                                            break
                                    if found_parent:
                                        break
                
                # Also check manual episode cache if not found yet
                if not found_parent:
                    try:
                        manual_cache = load_manual_episode_cache()
                        for series_id, series_seasons in manual_cache.items():
                            if found_parent:
                                break
                            if isinstance(series_seasons, dict):
                                for season_num, season_eps in series_seasons.items():
                                    if not isinstance(season_eps, dict):
                                        continue
                                    if mid in season_eps.values():
                                        # Found in manual cache, get series info from metadata
                                        series_meta = cache_data.get(series_id, {})
                                        series_title = series_meta.get('title', series_id)
                                        info_lines.append(f"\nSeries: {series_title}\n")
                                        # Find episode number
                                        for ep_num, ep_id in season_eps.items():
                                            if ep_id == mid:
                                                info_lines.append(f"Season {season_num}, Episode {ep_num}\n")
                                                found_parent = True
                                                break
                                        if found_parent:
                                            break
                    except Exception:
                        pass
            except Exception as e:
                # Silently ignore errors in episode lookup
                pass
        
        # For series, show seasons and episodes
        if meta.get('type', '').lower() == 'series':
            # Use totalSeasons if available
            total_seasons = meta.get('totalSeasons', 0)
            if total_seasons:
                info_lines.append(f"Seasons: {total_seasons}\n")
            
            # Count episodes from episodes dict structure
            episodes_dict = meta.get('episodes', {})
            if episodes_dict and isinstance(episodes_dict, dict):
                total_episodes = sum(len(season_eps) for season_eps in episodes_dict.values() if isinstance(season_eps, dict))
                if total_episodes > 0:
                    info_lines.append(f"Total Episodes: {total_episodes}\n")
        
        # Show summary/plot
        summary = meta.get('summary') or meta.get('plot') or ''
        if summary:
            info_lines.append(f"\nSummary:\n{summary}")
        
        if info_lines:
            self.info_text.insert('1.0', ''.join(info_lines))
        else:
            self.info_text.insert('1.0', '[No additional info]')
        
        self.info_text.config(state='disabled')

    def _on_select(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        
        # Get the actual label from the listbox (in case of filtering)
        selected_label = self.listbox.get(idx)
        
        # Find the corresponding match by label
        meta = None
        mid = None
        for lbl, m_id, m_meta in self.matches:
            if lbl == selected_label:
                mid = m_id
                meta = m_meta
                break
        
        if not meta:
            return
        
        # Update info text with metadata (pass mid for episode lookup)
        self._update_info_display(meta, mid if mid else None)

        # Invalidate older in-flight poster loads whenever selection changes.
        self._poster_request_token += 1
        request_token = self._poster_request_token
        
        poster_url = meta.get('poster_url') if meta else None
        if poster_url and requests and Image:
            # Capture modules into locals so the worker thread sees concrete module objects
            requests_mod = requests
            Image_mod = Image
            ImageTk_mod = ImageTk
            def _dl():
                try:
                    resp = requests_mod.get(poster_url, timeout=6)
                    resp.raise_for_status()
                    img = Image_mod.open(BytesIO(resp.content))
                    
                    # Auto-detect aspect ratio from image dimensions
                    orig_width, orig_height = img.size
                    if orig_height > 0:
                        aspect_ratio = orig_width / orig_height
                        # If wider than tall (landscape/thumbnail), use 16:9 aspect
                        # Otherwise use portrait poster aspect
                        if aspect_ratio > 1.0:
                            # Landscape/thumbnail - use 16:9
                            img_width, img_height = 240, 135
                        else:
                            # Portrait poster
                            img_width, img_height = 140, 200
                        
                        img_resized = img.resize((img_width, img_height), Image_mod.Resampling.LANCZOS)
                        def _set_img():
                            if request_token != self._poster_request_token:
                                return
                            if not self.winfo_exists() or not self.img_label.winfo_exists():
                                return
                            try:
                                self._poster_img = ImageTk_mod.PhotoImage(img_resized, master=self.img_label)
                                # Don't change label size, just update image
                                self.img_label.configure(image=self._poster_img, text='')
                            except tk.TclError:
                                # Window/widget likely destroyed while async load completed.
                                return
                            except Exception:
                                return
                        try:
                            self.after(0, _set_img)
                        except tk.TclError:
                            return
                except Exception as e:
                    # If image loading fails, show no image
                    print(f"Error loading poster from {poster_url}: {e}")
                    def _set_no_img():
                        if request_token != self._poster_request_token:
                            return
                        if not self.winfo_exists() or not self.img_label.winfo_exists():
                            return
                        try:
                            self.img_label.configure(text='[No Image]', image='')
                        except Exception:
                            pass
                    try:
                        self.after(0, _set_no_img)
                    except tk.TclError:
                        return
            threading.Thread(target=_dl, daemon=True).start()
        else:
            try:
                if self.winfo_exists() and self.img_label.winfo_exists():
                    self.img_label.configure(text='[No Image]', image='')
            except Exception:
                pass

    def _use_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        
        # Get the actual label from the listbox (in case of filtering)
        selected_label = self.listbox.get(idx)
        
        # Find the corresponding match by label
        mid = None
        for lbl, m_id, m_meta in self.matches:
            if lbl == selected_label:
                mid = m_id
                break
        
        if not mid:
            return
        
        # Return only the IMDb ID string to the callback
        try:
            self.on_choice(mid)
        except Exception:
            pass
        # If in a modal dialog, close the parent window
        try:
            self.winfo_toplevel().destroy()
        except Exception:
            pass

    def _get_selected_match(self):
        sel = self.listbox.curselection()
        if not sel:
            return None, None
        idx = sel[0]
        selected_label = self.listbox.get(idx)
        for lbl, m_id, m_meta in self.matches:
            if lbl == selected_label:
                return m_id, m_meta
        return None, None

    def _find_parent_series_id(self, episode_id: str):
        try:
            data = load_metadata()
            for series_id, series_meta in data.items():
                if str(series_meta.get('type', '')).lower() != 'series':
                    continue
                episodes = series_meta.get('episodes', {})
                if not isinstance(episodes, dict):
                    continue
                for season_eps in episodes.values():
                    if isinstance(season_eps, dict) and episode_id in season_eps.values():
                        return series_id
        except Exception:
            pass
        return None

    def _prompt_manual(self):
        # ask for manual imdb id in small dialog
        top = tk.Toplevel(self)
        top.title('Enter IMDb ID')
        tk.Label(top, text='Enter IMDb ID (e.g. tt1234567)').pack(padx=8, pady=6)
        entry = tk.Entry(top, width=24)
        entry.pack(padx=8, pady=6)
        def _ok():
            val = entry.get().strip()
            if val:
                try:
                    self.on_choice(val)
                except Exception:
                    pass
            try:
                top.destroy()
            except Exception:
                pass
            # If in a modal dialog, close the parent window
            try:
                self.winfo_toplevel().destroy()
            except Exception:
                pass
        tk.Button(top, text='OK', command=_ok).pack(pady=6)

    def _rescrape(self):
        """Signal to rescrape by returning special marker string."""
        try:
            self.on_choice("__RESCRAPE__")
        except Exception:
            pass
        try:
            self.winfo_toplevel().destroy()
        except Exception:
            pass
    
    def _refresh_from_omdb(self):
        """Refresh the selected entry's metadata from OMDB."""
        mid, _ = self._get_selected_match()
        
        if not mid:
            return
        
        # Import here to avoid circular imports
        try:
            from actions.omdb_gui_scraper import fetch_title_and_year_from_imdb_id
            import threading
            
            def worker():
                try:
                    # Fetch and update metadata from OMDB
                    # populate_episodes=True for series, fetch_poster=True for poster
                    fetch_title_and_year_from_imdb_id(mid, populate_episodes=True, fetch_poster=True)
                    
                    # Reload the matches to reflect updated data
                    self.after(0, lambda: self._reload_and_reselect(mid))
                except Exception as e:
                    print(f"Error refreshing metadata for {mid}: {e}")
            
            threading.Thread(target=worker, daemon=True).start()
        except Exception as e:
            print(f"Error starting refresh: {e}")

    def _repair_series_episodes(self):
        """Explicitly refresh the full episode mapping for the selected series."""
        mid, meta = self._get_selected_match()
        if not mid:
            return

        selected_type = str((meta or {}).get('type', '')).lower()
        series_id = mid if selected_type == 'series' else self._find_parent_series_id(mid)
        if not series_id:
            return

        try:
            from actions.omdb_gui_scraper import fetch_episode_ids_omdb
            import threading

            def worker():
                try:
                    fetch_episode_ids_omdb(series_id, {}, lambda: None, force_refresh=True)
                    self.after(0, lambda: self._reload_and_reselect(series_id))
                except Exception as e:
                    print(f"Error repairing series episode cache for {series_id}: {e}")

            threading.Thread(target=worker, daemon=True).start()
        except Exception as e:
            print(f"Error starting series episode repair: {e}")
    
    def _reload_and_reselect(self, imdb_id):
        """Reload matches and reselect the given IMDb ID."""
        try:
            # Reload metadata
            data = load_metadata()
            
            # Find and update the match in our list
            for i, (lbl, mid, meta) in enumerate(self.matches):
                if mid == imdb_id:
                    # Get updated metadata
                    updated_meta = data.get(imdb_id, {})
                    if updated_meta:
                        # Rebuild label
                        title = updated_meta.get('title', '')
                        year = updated_meta.get('year') or updated_meta.get('end_year') or ''
                        media_type = updated_meta.get('type', '').capitalize()
                        img_indicator = '📷 ' if updated_meta.get('poster_url') else ''
                        orphaned_tag = ' (Orphaned)' if media_type.lower() == 'episode' and self._is_orphaned_episode(mid, data) else ''
                        new_label = f"{img_indicator}{title} ({year}) [{mid}] ({media_type}){orphaned_tag}"
                        
                        # Update the match
                        self.matches[i] = (new_label, mid, updated_meta)
                    break
            
            # Refresh the display
            self._filter_listbox()
            
            # Try to reselect the item
            for i in range(self.listbox.size()):
                item_text = self.listbox.get(i)
                if imdb_id in item_text:
                    self.listbox.selection_clear(0, tk.END)
                    self.listbox.selection_set(i)
                    self.listbox.see(i)
                    self._on_select()
                    break
        except Exception as e:
            print(f"Error reloading data: {e}")

    def _use_original(self):
        """Use the original conflicting ID that was passed in."""
        try:
            # Use the conflicting_id parameter passed to __init__
            self.on_choice(self.conflicting_id if hasattr(self, 'conflicting_id') and self.conflicting_id else None)
        except Exception:
            pass
        try:
            self.winfo_toplevel().destroy()
        except Exception:
            pass

    def _cancel(self):
        try:
            self.on_choice(None)
        except Exception:
            pass
        # If in a modal dialog, close the parent window
        try:
            self.winfo_toplevel().destroy()
        except Exception:
            pass
