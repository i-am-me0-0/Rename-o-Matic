# gui/config_editor.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from config import cfg, CONFIG_FILE
from pathlib import Path
#import configparser


class ToggleSwitch(tk.Canvas):
    """A color-coded toggle switch widget."""
    def __init__(self, parent, width=50, height=24, **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0, **kwargs)
        self.width = width
        self.height = height
        self.is_on = False
        
        # Colors
        self.off_color = "#cccccc"
        self.on_color = "#4CAF50"
        
        # Draw switch
        self.bg_rect = self.create_rectangle(0, 0, width, height, fill=self.off_color, outline="", tags="bg")
        self.circle = self.create_oval(2, 2, height-2, height-2, fill="white", outline="", tags="circle")
        
        self.bind("<Button-1>", self.toggle)
        
    def toggle(self, event=None):
        self.is_on = not self.is_on
        self.update_visual()
        
    def set(self, value):
        """Set the switch state (True/False)."""
        self.is_on = bool(value)
        self.update_visual()
        
    def get(self):
        """Get the switch state."""
        return self.is_on
        
    def update_visual(self):
        if self.is_on:
            self.itemconfig("bg", fill=self.on_color)
            self.coords("circle", self.width - self.height + 2, 2, self.width - 2, self.height - 2)
        else:
            self.itemconfig("bg", fill=self.off_color)
            self.coords("circle", 2, 2, self.height - 2, self.height - 2)


class ConfigEditorWindow(tk.Frame):
    def __init__(self, master, on_back, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.on_back = on_back
        self.widgets = {}
        
        # Set minimum window size
        if hasattr(master, 'winfo_toplevel'):
            toplevel = master.winfo_toplevel()
            toplevel.geometry("710x700")
        
        # Configure the frame to expand
        self.pack(fill="both", expand=True)
        
        # Title
        title = tk.Label(self, text="Configuration Editor", font=("Arial", 14, "bold"))
        title.pack(pady=10)
        
        # Buttons at top
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(0, 10))
        
        tk.Button(btn_frame, text="Save Config", command=self.save_config, bg="#4CAF50", fg="white", width=15).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=on_back, width=15).pack(side="left", padx=5)
        
        # Simple scrollable container without canvas for testing
        container = tk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Build form directly in container
        self.build_form(container)
        
    def build_form(self, parent):
        """Build the configuration form."""
        
        # ============================================================================
        # Essential Settings
        # ============================================================================
        self.create_section_header(parent, "Essential Settings", "Edit these regularly")
        
        # [Paths]
        paths_frame = self.create_subsection(parent, "Media Library Paths")
        self.create_path_field(paths_frame, "movies_dir", "Movies Directory:", cfg["Paths"]["movies_dir"])
        self.create_path_field(paths_frame, "series_dir", "Series Directory:", cfg["Paths"]["series_dir"])
        
        # [OMDb]
        omdb_frame = self.create_subsection(parent, "OMDb API")
        self.create_text_field(omdb_frame, "omdb_api_key", "API Key:", cfg["OMDb"]["omdb_api_key"], 
                               help_text="Get one at http://www.omdbapi.com/apikey.aspx")
        
        # [SeriesAliases]
        aliases_frame = self.create_subsection(parent, "Series Aliases")
        self.create_text_area(aliases_frame, "series_aliases", 
                             "Map folder names to canonical names (one per line: folder = Series Name):",
                             self.format_aliases_for_display())
        
        # ============================================================================
        # General Settings
        # ============================================================================
        self.create_section_header(parent, "General Settings", "Occasionally adjusted")
        
        # [General]
        general_frame = self.create_subsection(parent, "General Options")
        
        self.create_text_field(general_frame, "lang_codes", "Subtitle Language Codes:", 
                              cfg["General"]["lang_codes"],
                              help_text="e.g. ', en, nl' (leading comma = files without lang tag)")
        
        self.create_dropdown(general_frame, "movie_folder_location", "Movie Folder Location:",
                           cfg["General"]["movie_folder_location"],
                           ["root", "source"],
                           help_text="root = in movies_dir | source = keep in original subfolder")
        
        self.create_toggle(general_frame, "create_movie_subfolders", "Create Movie Subfolders:",
                          cfg["General"].get("create_movie_subfolders", "false").lower() == "true")
        
        self.create_dropdown(general_frame, "default_include", "Default Include in Preview:",
                           cfg["General"]["default_include"],
                           ["1", "0"],
                           help_text="1 = checked by default | 0 = unchecked")
        
        self.create_toggle(general_frame, "prepend_episode_title_to_extras", "Include Episode Title in Extras:",
                          cfg["General"]["prepend_episode_title_to_extras"].lower() == "true")
        
        self.create_toggle(general_frame, "debug_mode", "Console Debug Output:",
                          cfg["General"].get("debug_mode", "false").lower() == "true",
                          help_text="Shows internal processing details")
        
        self.create_toggle(general_frame, "ui_debug", "UI Debug Output:",
                          cfg["General"].get("ui_debug", "false").lower() == "true",
                          help_text="Shows detailed GUI diagnostics")
        
        self.create_text_field(general_frame, "skip_imdb_ids", "Skip IMDb IDs (comma-separated):",
                              cfg["General"].get("skip_imdb_ids", ""))
        
        # [Extensions]
        ext_frame = self.create_subsection(parent, "File Extensions")
        self.create_text_field(ext_frame, "video_ext", "Video Extensions (comma-separated):",
                              cfg["Extensions"]["video"])
        self.create_text_field(ext_frame, "subtitle_ext", "Subtitle Extensions (comma-separated):",
                              cfg["Extensions"]["subtitle"])
        
        # [Series]
        series_frame = self.create_subsection(parent, "Series Options")
        self.create_text_field(series_frame, "edge_keywords", "Edge Episode Keywords (comma-separated):",
                              cfg["Series"].get("edge_keywords", ""),
                              help_text="Keywords that indicate special/edge episodes")
        
        
    
    def create_section_header(self, parent, title, subtitle):
        """Create a major section header."""
        frame = tk.Frame(parent, bg="#2196F3", height=50)
        frame.pack(fill="x", pady=(20, 0))
        tk.Label(frame, text=title, font=("Arial", 12, "bold"), bg="#2196F3", fg="white").pack(anchor="w", padx=10, pady=(5, 0))
        tk.Label(frame, text=subtitle, font=("Arial", 9), bg="#2196F3", fg="white").pack(anchor="w", padx=10, pady=(0, 5))
        
    def create_subsection(self, parent, title):
        """Create a subsection frame."""
        frame = tk.LabelFrame(parent, text=title, font=("Arial", 10, "bold"), padx=10, pady=10)
        frame.pack(fill="x", padx=10, pady=10)
        return frame
        
    def create_text_field(self, parent, key, label, value, help_text=None):
        """Create a text field."""
        row = tk.Frame(parent)
        row.pack(fill="x", pady=5)
        tk.Label(row, text=label, width=25, anchor="w").pack(side="left")
        entry = tk.Entry(row)
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        self.widgets[key] = entry
        if help_text:
            tk.Label(row, text=help_text, font=("Arial", 8), fg="gray").pack(side="left", padx=5)
    
    def create_path_field(self, parent, key, label, value):
        """Create a path field with browse button."""
        row = tk.Frame(parent)
        row.pack(fill="x", pady=5)
        tk.Label(row, text=label, width=25, anchor="w").pack(side="left")
        entry = tk.Entry(row)
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(row, text="Browse...", command=lambda: self.browse_folder(entry)).pack(side="left")
        self.widgets[key] = entry
        
    def create_toggle(self, parent, key, label, value, help_text=None):
        """Create a toggle switch."""
        row = tk.Frame(parent)
        row.pack(fill="x", pady=5)
        tk.Label(row, text=label, width=25, anchor="w").pack(side="left")
        switch = ToggleSwitch(row)
        switch.set(value)
        switch.pack(side="left", padx=5)
        self.widgets[key] = switch
        if help_text:
            tk.Label(row, text=help_text, font=("Arial", 8), fg="gray").pack(side="left", padx=5)
        
    def create_dropdown(self, parent, key, label, value, options, help_text=None):
        """Create a dropdown."""
        row = tk.Frame(parent)
        row.pack(fill="x", pady=5)
        tk.Label(row, text=label, width=25, anchor="w").pack(side="left")
        var = tk.StringVar(value=value)
        dropdown = ttk.Combobox(row, textvariable=var, values=options, state="readonly", width=25)
        dropdown.pack(side="left", padx=5)
        self.widgets[key] = var
        if help_text:
            tk.Label(row, text=help_text, font=("Arial", 8), fg="gray").pack(side="left", padx=5)
    
    def create_text_area(self, parent, key, label, value):
        """Create a text area."""
        tk.Label(parent, text=label, anchor="w").pack(fill="x", pady=(5, 2))
        text = tk.Text(parent, height=6, wrap="word")
        text.insert("1.0", value)
        text.pack(fill="both", expand=True, pady=5)
        self.widgets[key] = text
        
    def browse_folder(self, entry):
        """Open folder browser."""
        folder = filedialog.askdirectory(initialdir=entry.get())
        if folder:
            entry.delete(0, tk.END)
            entry.insert(0, folder)
    
    def format_aliases_for_display(self):
        """Format series aliases for text area display."""
        if "SeriesAliases" not in cfg:
            return ""
        lines = []
        for key, value in cfg["SeriesAliases"].items():
            lines.append(f"{key} = {value}")
        return "\n".join(lines)
    
    def parse_aliases_from_text(self, text):
        """Parse series aliases from text area."""
        aliases = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                aliases[key.strip()] = value.strip()
        return aliases
    
    def save_config(self):
        """Save the configuration."""
        try:
            # Collect changes
            changes = []
            
            # Check Paths
            if self.widgets["movies_dir"].get() != cfg["Paths"]["movies_dir"]:
                changes.append(("Paths", "movies_dir", cfg["Paths"]["movies_dir"], self.widgets["movies_dir"].get()))
            if self.widgets["series_dir"].get() != cfg["Paths"]["series_dir"]:
                changes.append(("Paths", "series_dir", cfg["Paths"]["series_dir"], self.widgets["series_dir"].get()))
            
            # Check OMDb
            if self.widgets["omdb_api_key"].get() != cfg["OMDb"]["omdb_api_key"]:
                changes.append(("OMDb", "omdb_api_key", cfg["OMDb"]["omdb_api_key"], self.widgets["omdb_api_key"].get()))
            
            # Check SeriesAliases
            old_aliases = self.format_aliases_for_display()
            new_aliases = self.widgets["series_aliases"].get("1.0", tk.END).strip()
            if old_aliases != new_aliases:
                changes.append(("SeriesAliases", "(all)", old_aliases[:50] + "..." if len(old_aliases) > 50 else old_aliases, 
                              new_aliases[:50] + "..." if len(new_aliases) > 50 else new_aliases))
            
            # Check General
            if self.widgets["lang_codes"].get() != cfg["General"]["lang_codes"]:
                changes.append(("General", "lang_codes", cfg["General"]["lang_codes"], self.widgets["lang_codes"].get()))
            if self.widgets["movie_folder_location"].get() != cfg["General"]["movie_folder_location"]:
                changes.append(("General", "movie_folder_location", cfg["General"]["movie_folder_location"], self.widgets["movie_folder_location"].get()))
            
            old_subfolders = cfg["General"].get("create_movie_subfolders", "false").lower() == "true"
            new_subfolders = self.widgets["create_movie_subfolders"].get()
            if old_subfolders != new_subfolders:
                changes.append(("General", "create_movie_subfolders", str(old_subfolders).lower(), str(new_subfolders).lower()))
            
            if self.widgets["default_include"].get() != cfg["General"]["default_include"]:
                changes.append(("General", "default_include", cfg["General"]["default_include"], self.widgets["default_include"].get()))
            
            old_prepend = cfg["General"]["prepend_episode_title_to_extras"].lower() == "true"
            new_prepend = self.widgets["prepend_episode_title_to_extras"].get()
            if old_prepend != new_prepend:
                changes.append(("General", "prepend_episode_title_to_extras", str(old_prepend), str(new_prepend)))
            
            old_debug = cfg["General"].get("debug_mode", "false").lower() == "true"
            new_debug = self.widgets["debug_mode"].get()
            if old_debug != new_debug:
                changes.append(("General", "debug_mode", str(old_debug), str(new_debug)))
            
            old_ui_debug = cfg["General"].get("ui_debug", "false").lower() == "true"
            new_ui_debug = self.widgets["ui_debug"].get()
            if old_ui_debug != new_ui_debug:
                changes.append(("General", "ui_debug", str(old_ui_debug), str(new_ui_debug)))
            
            if self.widgets["skip_imdb_ids"].get() != cfg["General"].get("skip_imdb_ids", ""):
                changes.append(("General", "skip_imdb_ids", cfg["General"].get("skip_imdb_ids", ""), self.widgets["skip_imdb_ids"].get()))
            
            # Check Extensions
            if self.widgets["video_ext"].get() != cfg["Extensions"]["video"]:
                changes.append(("Extensions", "video", cfg["Extensions"]["video"], self.widgets["video_ext"].get()))
            if self.widgets["subtitle_ext"].get() != cfg["Extensions"]["subtitle"]:
                changes.append(("Extensions", "subtitle", cfg["Extensions"]["subtitle"], self.widgets["subtitle_ext"].get()))
            
            # Check Series
            if self.widgets["edge_keywords"].get() != cfg["Series"].get("edge_keywords", ""):
                changes.append(("Series", "edge_keywords", cfg["Series"].get("edge_keywords", ""), self.widgets["edge_keywords"].get()))
            
            # If no changes, inform user
            if not changes:
                messagebox.showinfo("No Changes", "No configuration changes detected.")
                return
            
            # Show confirmation dialog
            if not self.confirm_changes(changes):
                return
            
            # Apply changes to config file while preserving comments
            self.apply_changes_to_file(changes)
            
            messagebox.showinfo("Success", "Configuration saved successfully.\nRestart the application for changes to take effect.")
            self.on_back()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration:\n{e}")
    
    def confirm_changes(self, changes):
        """Show confirmation dialog with before/after changes."""
        dialog = tk.Toplevel(self)
        dialog.title("Confirm Configuration Changes")
        dialog.geometry("700x500")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        
        tk.Label(dialog, text="The following changes will be made:", font=("Arial", 12, "bold")).pack(pady=10)
        
        # Scrollable frame for changes
        canvas = tk.Canvas(dialog)
        scrollbar = tk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas)
        
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Display changes
        for section, key, old_val, new_val in changes:
            change_frame = tk.Frame(scrollable, relief="solid", borderwidth=1, padx=10, pady=10)
            change_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(change_frame, text=f"[{section}] {key}", font=("Arial", 10, "bold")).pack(anchor="w")
            
            old_frame = tk.Frame(change_frame)
            old_frame.pack(fill="x", pady=2)
            tk.Label(old_frame, text="Before:", fg="red", font=("Arial", 9, "bold")).pack(side="left")
            tk.Label(old_frame, text=old_val, font=("Arial", 9)).pack(side="left", padx=5)
            
            new_frame = tk.Frame(change_frame)
            new_frame.pack(fill="x", pady=2)
            tk.Label(new_frame, text="After:", fg="green", font=("Arial", 9, "bold")).pack(side="left")
            tk.Label(new_frame, text=new_val, font=("Arial", 9)).pack(side="left", padx=5)
        
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)
        
        # Buttons
        result = {"confirmed": False}
        
        def confirm():
            result["confirmed"] = True
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Apply Changes", command=confirm, bg="#4CAF50", fg="white", width=15).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=cancel, width=15).pack(side="left", padx=5)
        
        dialog.wait_window()
        return result["confirmed"]
    
    def apply_changes_to_file(self, changes):
        """Apply changes to config file while preserving comments and structure."""
        # Read original file
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Parse changes into a dict for easier lookup
        changes_dict = {}
        for section, key, old_val, new_val in changes:
            if section not in changes_dict:
                changes_dict[section] = {}
            changes_dict[section][key] = new_val
        
        # Process lines
        current_section = None
        new_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check for section headers
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1]
                new_lines.append(line)
                i += 1
                continue
            
            # Check if this is a key=value line
            if "=" in line and not stripped.startswith("#") and current_section:
                key = line.split("=")[0].strip()
                
                # Handle SeriesAliases specially
                if current_section == "SeriesAliases" and "(all)" in changes_dict.get("SeriesAliases", {}):
                    # Skip all old alias lines
                    while i < len(lines) and not lines[i].strip().startswith("["):
                        if lines[i].strip() and not lines[i].strip().startswith("#"):
                            i += 1
                        else:
                            new_lines.append(lines[i])
                            i += 1
                    
                    # Add new aliases
                    aliases = self.parse_aliases_from_text(self.widgets["series_aliases"].get("1.0", tk.END))
                    for alias_key, alias_value in aliases.items():
                        new_lines.append(f"{alias_key} = {alias_value}\n")
                    continue
                
                # Check if we need to update this key
                if current_section in changes_dict and key in changes_dict[current_section]:
                    new_value = changes_dict[current_section][key]
                    # Preserve indentation and comments
                    indent = len(line) - len(line.lstrip())
                    # Handle boolean values properly
                    if key in ["debug_mode", "ui_debug", "prepend_episode_title_to_extras", "create_movie_subfolders"]:
                        new_value = "True" if str(new_value).lower() in ["true", "1"] else "False"
                    new_lines.append(" " * indent + f"{key} = {new_value}\n")
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
            
            i += 1
        
        # Write back
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)