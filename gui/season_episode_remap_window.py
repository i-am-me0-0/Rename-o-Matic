import tkinter as tk
from tkinter import ttk

from actions.season_episode_remap import (
    apply_season_remap_to_manual_cache,
    get_episode_title_map,
    get_series_season_map,
)
from core.media_metadata_cache import get_entry
from gui.existing_cache_picker import ExistingCachePickerFrame


class SeasonEpisodeRemapWindow(tk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)

        tk.Label(self, text="Season Episode Remap", font=("Arial", 14, "bold")).pack(pady=(10, 2))
        tk.Label(
            self,
            text="Select show, pick season, then fix with simple actions and apply to manual episode cache",
            font=("Arial", 9),
            fg="gray",
        ).pack(pady=(0, 8))

        tk.Label(
            self,
            text="Source episodes are loaded from cache/media_metadata.json → <series_id>.episodes.<season>",
            font=("Arial", 9),
            fg="#555",
        ).pack(pady=(0, 8))

        form = tk.Frame(self)
        form.pack(fill="x", padx=12)

        select_frame = ttk.LabelFrame(form, text="1) Select Series and Season")
        select_frame.pack(fill="x", pady=(0, 8))

        edit_frame = ttk.LabelFrame(form, text="2) Edit Mapping")
        edit_frame.pack(fill="x", pady=(0, 8))

        save_frame = ttk.LabelFrame(form, text="3) Save")
        save_frame.pack(fill="x")

        self.series_id_var = tk.StringVar(value="")
        self.series_title_var = tk.StringVar(value="No show selected")
        self.season_var = tk.StringVar(value="")
        self.local_episode_var = tk.StringVar(value="")
        self.source_episode_var = tk.StringVar(value="")
        self.manual_imdb_var = tk.StringVar(value="")
        self.clear_existing_var = tk.BooleanVar(value=False)

        row = 0
        tk.Button(select_frame, text="Select Show (Cache Picker)", command=self.open_series_picker).grid(row=row, column=0, sticky="w", padx=(8, 8), pady=6)
        tk.Label(select_frame, textvariable=self.series_title_var, anchor="w").grid(row=row, column=1, columnspan=5, sticky="w", pady=6)

        row += 1
        tk.Label(select_frame, text="Season:").grid(row=row, column=0, sticky="w", padx=(8, 6), pady=6)
        self.season_combo = ttk.Combobox(select_frame, textvariable=self.season_var, state="readonly", width=10)
        self.season_combo.grid(row=row, column=1, sticky="w", pady=6)
        tk.Button(select_frame, text="Load Source Season", command=self.load_selected_season).grid(row=row, column=2, sticky="w", padx=(8, 0), pady=6)

        row = 0
        tk.Label(edit_frame, text="Target Episode:").grid(row=row, column=0, sticky="w", padx=(8, 6), pady=6)
        self.local_episode_combo = ttk.Combobox(edit_frame, textvariable=self.local_episode_var, state="readonly", width=10)
        self.local_episode_combo.grid(row=row, column=1, sticky="w", pady=6)

        tk.Label(edit_frame, text="Source Episode:").grid(row=row, column=2, sticky="w", padx=(16, 6), pady=6)
        self.source_episode_combo = ttk.Combobox(edit_frame, textvariable=self.source_episode_var, state="readonly", width=10)
        self.source_episode_combo.grid(row=row, column=3, sticky="w", pady=6)

        row += 1
        tk.Label(edit_frame, text="Manual IMDb ID:").grid(row=row, column=0, sticky="w", padx=(8, 6), pady=6)
        tk.Entry(edit_frame, textvariable=self.manual_imdb_var, width=20).grid(row=row, column=1, sticky="w", pady=6)
        tk.Label(edit_frame, text="(format: tt1234567)", fg="gray").grid(row=row, column=2, columnspan=2, sticky="w", pady=6)

        tk.Checkbutton(
            save_frame,
            text="Clear existing manual cache mappings for this season before save",
            variable=self.clear_existing_var,
        ).pack(side="left", padx=(8, 8), pady=6)

        btns = tk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(2, 8))
        tk.Button(btns, text="Set Target from Source", command=self.link_local_to_source).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Set Target to Manual ID", command=self.link_local_to_manual_id).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Add Episode at End", command=self.add_episode_at_end).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Shift Forward (+1) from Target", command=self.propagate_from_local).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Delete Target Mapping", command=self.remove_local_episode).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Reset Working Map to Source", command=self.reset_to_source).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Save to Manual Episode Cache", command=self.apply_remap).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Close", command=self._close).pack(side="right")

        splitter = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        splitter.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        left = tk.Frame(splitter)
        right = tk.Frame(splitter)
        splitter.add(left, weight=1)
        splitter.add(right, weight=1)

        tk.Label(left, text="Source season map (metadata):", anchor="w").pack(fill="x")
        self.source_text = tk.Text(left, height=18, width=60)
        self.source_text.pack(fill="both", expand=True)

        tk.Label(right, text="Working remap (will be saved to manual cache):", anchor="w").pack(fill="x")
        self.preview_text = tk.Text(right, height=18, width=60)
        self.preview_text.pack(fill="both", expand=True)

        self.status_label = tk.Label(self, text="", fg="gray")
        self.status_label.pack(fill="x", padx=12, pady=(0, 10))

        self._source_map = {}
        self._working_map = {}

    def open_series_picker(self):
        picker_win = tk.Toplevel(self)
        picker_win.title("Select Series")

        def on_choice(selected_id):
            if not selected_id:
                return
            self.series_id_var.set(str(selected_id))
            entry = get_entry(selected_id) or {}
            title = entry.get("title") or "Unknown"
            year = entry.get("year") or ""
            self.series_title_var.set(f"{title} ({year}) [{selected_id}]")
            self._load_season_values(entry)
            try:
                picker_win.destroy()
            except Exception:
                pass

        frame = ExistingCachePickerFrame(
            picker_win,
            name="",
            conflicting_id="",
            on_choice=on_choice,
            filter_type="series",
        )
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        picker_win.geometry("980x620")

    def _load_season_values(self, series_entry):
        episodes = series_entry.get("episodes", {}) if isinstance(series_entry, dict) else {}
        seasons = []
        if isinstance(episodes, dict):
            for key in episodes.keys():
                try:
                    seasons.append(int(key))
                except Exception:
                    continue
        seasons = sorted(set(seasons))
        values = [str(x) for x in seasons]
        self.season_combo["values"] = values
        if values:
            self.season_var.set(values[0])
            self.load_selected_season()
        else:
            self.season_var.set("")
            self._source_map = {}
            self._working_map = {}
            self._render_maps()

    def _close(self):
        try:
            self.master.destroy()
        except Exception:
            pass

    def _parse_header(self):
        series_id = self.series_id_var.get().strip()
        season_raw = self.season_var.get().strip()
        if not series_id:
            raise ValueError("Series IMDb ID is required")
        if not season_raw:
            raise ValueError("Season is required")
        season = int(season_raw)
        if season <= 0:
            raise ValueError("Season must be > 0")
        return series_id, season

    def _title_for(self, imdb_id, title_map):
        title = title_map.get(str(imdb_id), "")
        return f" | {title}" if title else ""

    def _refresh_episode_dropdowns(self):
        eps = sorted(set(list(self._source_map.keys()) + list(self._working_map.keys())))
        if eps:
            max_ep = max(eps)
            local_values = [str(i) for i in range(1, max_ep + 2)]
            source_values = [str(i) for i in eps]
        else:
            local_values = []
            source_values = []

        self.local_episode_combo["values"] = local_values
        self.source_episode_combo["values"] = source_values

        if local_values and not self.local_episode_var.get():
            self.local_episode_var.set(local_values[0])
        if source_values and not self.source_episode_var.get():
            self.source_episode_var.set(source_values[0])

    def load_selected_season(self):
        try:
            series_id, season = self._parse_header()
            self._source_map = get_series_season_map(series_id, season)
            if not self._source_map:
                self._working_map = {}
                self._render_maps()
                self.status_label.config(text="No season data found in media metadata cache", fg="orange")
                return
            self._working_map = dict(self._source_map)
            self._refresh_episode_dropdowns()
            self._render_maps()

            self.status_label.config(text=f"Loaded source mapping: {len(self._source_map)} episodes", fg="green")
        except Exception as e:
            self.status_label.config(text=f"Load error: {e}", fg="red")

    def _render_maps(self):
        title_map = get_episode_title_map()

        self.source_text.delete("1.0", tk.END)
        if not self._source_map:
            self.source_text.insert(tk.END, "(No source map loaded)\n")
        else:
            for ep_num in sorted(self._source_map.keys()):
                imdb_id = self._source_map[ep_num]
                self.source_text.insert(tk.END, f"E{ep_num:02}: {imdb_id}{self._title_for(imdb_id, title_map)}\n")

        self.preview_text.delete("1.0", tk.END)
        if not self._working_map:
            self.preview_text.insert(tk.END, "(No working remap)\n")
        else:
            for ep_num in sorted(self._working_map.keys()):
                imdb_id = self._working_map[ep_num]
                self.preview_text.insert(tk.END, f"E{ep_num:02}: {imdb_id}{self._title_for(imdb_id, title_map)}\n")

    def _selected_local_episode(self):
        raw = self.local_episode_var.get().strip()
        if not raw:
            raise ValueError("Choose a Local Ep")
        return int(raw)

    def _selected_source_episode(self):
        raw = self.source_episode_var.get().strip()
        if not raw:
            raise ValueError("Choose a Source Ep")
        return int(raw)

    def propagate_from_local(self):
        try:
            ep = self._selected_local_episode()
            if not self._working_map:
                raise ValueError("Load a season first")
            max_ep = max(self._working_map.keys()) if self._working_map else ep
            for key in range(max_ep, ep - 1, -1):
                if key in self._working_map:
                    self._working_map[key + 1] = self._working_map[key]
            if ep in self._working_map:
                del self._working_map[ep]
            self._refresh_episode_dropdowns()
            self._render_maps()
            self.status_label.config(text=f"Propagated +1 from E{ep:02}", fg="green")
        except Exception as e:
            self.status_label.config(text=f"Propagate error: {e}", fg="red")

    def remove_local_episode(self):
        try:
            ep = self._selected_local_episode()
            if ep in self._working_map:
                del self._working_map[ep]
            self._refresh_episode_dropdowns()
            self._render_maps()
            self.status_label.config(text=f"Removed local mapping for E{ep:02}", fg="green")
        except Exception as e:
            self.status_label.config(text=f"Remove error: {e}", fg="red")

    def link_local_to_source(self):
        try:
            local_ep = self._selected_local_episode()
            source_ep = self._selected_source_episode()
            imdb_id = self._source_map.get(source_ep)
            if not imdb_id:
                raise ValueError(f"No source mapping at E{source_ep:02}")
            self._working_map[local_ep] = imdb_id
            self._refresh_episode_dropdowns()
            self._render_maps()
            self.status_label.config(text=f"Linked E{local_ep:02} <- source E{source_ep:02}", fg="green")
        except Exception as e:
            self.status_label.config(text=f"Link error: {e}", fg="red")

    def link_local_to_manual_id(self):
        try:
            local_ep = self._selected_local_episode()
            imdb_id = self.manual_imdb_var.get().strip()
            if not imdb_id.startswith("tt"):
                raise ValueError("Manual IMDb ID must start with 'tt'")
            self._working_map[local_ep] = imdb_id
            self._refresh_episode_dropdowns()
            self._render_maps()
            self.status_label.config(text=f"Linked E{local_ep:02} <- {imdb_id}", fg="green")
        except Exception as e:
            self.status_label.config(text=f"Manual link error: {e}", fg="red")

    def add_episode_at_end(self):
        try:
            if not self._working_map and not self._source_map:
                raise ValueError("Load a season first")

            max_existing = 0
            if self._working_map:
                max_existing = max(self._working_map.keys())
            elif self._source_map:
                max_existing = max(self._source_map.keys())
            target_ep = max_existing + 1

            manual_id = self.manual_imdb_var.get().strip()
            source_ep = None
            source_id = None
            try:
                source_ep = self._selected_source_episode()
                source_id = self._source_map.get(source_ep)
            except Exception:
                source_ep = None
                source_id = None

            if manual_id and manual_id.startswith("tt"):
                imdb_id = manual_id
                label = f"manual {manual_id}"
            elif source_id:
                imdb_id = source_id
                source_ep_num = source_ep if isinstance(source_ep, int) else -1
                label = f"source E{source_ep_num:02}"
            else:
                raise ValueError("Enter Manual IMDb ID or choose a valid Source Episode")

            self._working_map[target_ep] = imdb_id
            self.local_episode_var.set(str(target_ep))
            self._refresh_episode_dropdowns()
            self._render_maps()
            self.status_label.config(text=f"Added E{target_ep:02} from {label}", fg="green")
        except Exception as e:
            self.status_label.config(text=f"Add episode error: {e}", fg="red")

    def reset_to_source(self):
        self._working_map = dict(self._source_map)
        self._refresh_episode_dropdowns()
        self._render_maps()
        self.status_label.config(text="Working map reset to source", fg="green")

    def apply_remap(self):
        try:
            series_id, season = self._parse_header()
            remap = dict(sorted(self._working_map.items()))
            if not remap:
                raise ValueError("No working mapping to apply")

            saved = apply_season_remap_to_manual_cache(
                series_imdb_id=series_id,
                season=season,
                remap=remap,
                manual_overrides=None,
                clear_existing_season=self.clear_existing_var.get(),
            )

            self._working_map = dict(saved)
            self._refresh_episode_dropdowns()
            self._render_maps()
            self.status_label.config(
                text=f"Applied to manual cache: {len(saved)} total season entries now saved",
                fg="green",
            )
        except Exception as e:
            self.status_label.config(text=f"Apply error: {e}", fg="red")
