import tkinter as tk
from typing import Optional
import threading
from actions.omdb_gui_scraper import safe_request, search_omdb, get_root, fetch_title_and_year_from_imdb_id
from core.media_metadata_cache import set_entry, get_entry
from gui.picker import Picker


class OMDBScraperWindow(tk.Frame):
    """Window for manually scraping OMDB data to fill missing metadata."""
    
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        
        # Title
        tk.Label(self, text="OMDB Metadata Scraper", font=("Arial", 14, "bold")).pack(pady=10)
        tk.Label(self, text="Manually search and add metadata to cache", font=("Arial", 10)).pack()
        
        # Search input frame
        search_frame = tk.Frame(self)
        search_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(search_frame, text="Search Title:").pack(side='left', padx=(0,5))
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side='left', fill='x', expand=True, padx=(0,5))
        search_entry.bind('<Return>', lambda e: self.do_search())
        tk.Button(search_frame, text="Search", command=self.do_search).pack(side='left')
        # Close button
        tk.Button(search_frame, text="Close", command=self.close_window).pack(side='left')
        
        # Create scrollable container for picker
        scroll_container = tk.Frame(self)
        scroll_container.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Canvas and scrollbar
        self.canvas = tk.Canvas(scroll_container)
        scrollbar = tk.Scrollbar(scroll_container, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        
        # Picker container inside canvas
        self.picker_container = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.picker_container, anchor='nw')
        
        # Configure scrolling
        def configure_scroll_region(event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        
        def configure_canvas_width(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        
        self.picker_container.bind('<Configure>', configure_scroll_region)
        self.canvas.bind('<Configure>', configure_canvas_width)
        
        # Mouse wheel scrolling
        def on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        self.canvas.bind_all('<MouseWheel>', on_mousewheel)
        
        # Status label
        self.status_label = tk.Label(self, text="Enter a title or IMDb ID (tt...) to search", font=("Arial", 9), fg="gray")
        self.status_label.pack(pady=10)
        
        
        
        self.current_picker = None
    
    def close_window(self):
        """Close the window."""
        try:
            self.master.destroy()
        except Exception:
            pass
        
    def do_search(self):
        """Search OMDB and show results in Picker."""
        search_title = self.search_var.get().strip()
        if not search_title:
            self.status_label.config(text="Please enter a search title or IMDb ID", fg="red")
            return
        
        # Clear existing picker
        if self.current_picker:
            self.current_picker.destroy()
            self.current_picker = None
        
        self.status_label.config(text=f"Searching for '{search_title}'...", fg="blue")
        
        def worker():
            try:
                results = search_omdb(search_title)
                def show_picker():
                    if results or search_title.startswith('tt'):
                        # Create picker with results
                        self.current_picker = Picker(
                            self.picker_container,
                            original_line=search_title,
                            search_title=search_title,
                            results=results,
                            source='manual'
                        )
                        self.current_picker.pack(fill='both', expand=True)
                        
                        # Find and reconfigure the buttons in the picker
                        # The buttons are in the top_frame (first child of picker)
                        for widget in self.current_picker.winfo_children():
                            if isinstance(widget, tk.Frame):
                                for child in widget.winfo_children():
                                    if isinstance(child, tk.Button):
                                        btn_text = child.cget('text')
                                        if btn_text == "Confirm Selection":
                                            child.config(command=self.handle_picker_selection)
                                        elif btn_text == "Skip":
                                            child.config(command=lambda: self.status_label.config(text="Skipped", fg="gray"))
                                        elif btn_text == "Cancel":
                                            child.config(command=lambda: self.status_label.config(text="Cancelled", fg="gray"))
                        
                        if results:
                            self.status_label.config(text=f"Found {len(results)} results - select one and click Confirm Selection", fg="green")
                        else:
                            self.status_label.config(text="No results found - you can enter an IMDb ID directly", fg="orange")
                    else:
                        self.status_label.config(text="No results found", fg="orange")
                
                self.after(0, show_picker)
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"Error: {e}", fg="red"))
        
        threading.Thread(target=worker, daemon=True).start()
    
    def handle_picker_selection(self):
        """Handle the confirmed selection from picker."""
        if not self.current_picker:
            return
        
        selection = self.current_picker.selection
        if not selection:
            self.status_label.config(text="No selection made", fg="gray")
            return
        
        imdb_id = selection.get('imdbID')
        if not imdb_id:
            self.status_label.config(text="Selected result has no IMDb ID", fg="red")
            return
        
        # Close the picker first
        self.current_picker.destroy()
        self.current_picker = None
        
        self.status_label.config(text=f"Adding {imdb_id} to cache...", fg="blue")
        
        def worker():
            try:
                # Fetch metadata from OMDB (includes type detection, episodes, poster)
                result = fetch_title_and_year_from_imdb_id(imdb_id, populate_episodes=True, fetch_poster=True)
                
                # Verify it's in cache
                entry = get_entry(imdb_id)
                if entry:
                    title = entry.get('title', 'Unknown')
                    media_type = entry.get('type', 'unknown')
                    self.after(0, lambda: self.status_label.config(
                        text=f"Successfully added '{title}' [{imdb_id}] ({media_type}) to cache", 
                        fg="green"
                    ))
                else:
                    self.after(0, lambda: self.status_label.config(
                        text=f"Metadata fetched but could not verify in cache", 
                        fg="orange"
                    ))
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"Error: {e}", fg="red"))
        
        threading.Thread(target=worker, daemon=True).start()

