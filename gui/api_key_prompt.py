# gui/api_key_prompt.py
import tkinter as tk
from tkinter import messagebox
import webbrowser


def prompt_for_api_key(config_file):
    """Show a dialog to prompt for OMDb API key."""
    root = tk.Tk()
    root.title("OMDb API Key Required")
    root.geometry("500x250")
    root.resizable(False, False)
    
    # Center window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (500 // 2)
    y = (root.winfo_screenheight() // 2) - (250 // 2)
    root.geometry(f"+{x}+{y}")
    
    # Title
    tk.Label(root, text="OMDb API Key Required", font=("Arial", 14, "bold")).pack(pady=15)
    
    # Instructions
    tk.Label(root, text="This app requires an OMDb API key to fetch movie/series metadata.", 
             font=("Arial", 10)).pack(pady=5)
    
    # Link frame
    link_frame = tk.Frame(root)
    link_frame.pack(pady=10)
    
    tk.Label(link_frame, text="Get a free API key at:", font=("Arial", 10)).pack(side="left", padx=5)
    
    url = "http://www.omdbapi.com/apikey.aspx"
    link_label = tk.Label(link_frame, text=url, font=("Arial", 10), fg="blue", cursor="hand2")
    link_label.pack(side="left")
    link_label.bind("<Button-1>", lambda e: webbrowser.open(url))
    
    # Entry frame
    entry_frame = tk.Frame(root)
    entry_frame.pack(pady=15)
    
    tk.Label(entry_frame, text="Enter your API key:", font=("Arial", 10)).pack(anchor="w")
    api_key_var = tk.StringVar()
    entry = tk.Entry(entry_frame, textvariable=api_key_var, width=40, font=("Arial", 10))
    entry.pack(pady=5)
    entry.focus_set()
    
    result = {"saved": False}
    
    def save_key():
        key = api_key_var.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter an API key.")
            return
        
        try:
            # Read existing config
            with open(config_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Update only the omdb_api_key line
            new_lines = []
            for line in lines:
                if line.strip().startswith("omdb_api_key"):
                    # Preserve indentation and comments
                    indent = len(line) - len(line.lstrip())
                    new_lines.append(" " * indent + f"omdb_api_key = {key}\n")
                else:
                    new_lines.append(line)
            
            # Write back
            with open(config_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            
            result["saved"] = True
            root.destroy()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save API key:\n{e}")
    
    def cancel():
        root.destroy()
    
    # Buttons
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)
    
    tk.Button(btn_frame, text="Save & Continue", command=save_key, bg="#4CAF50", fg="white", 
              width=15, font=("Arial", 10)).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Cancel", command=cancel, width=15, 
              font=("Arial", 10)).pack(side="left", padx=5)
    
    # Bind Enter key to save
    root.bind("<Return>", lambda e: save_key())
    
    root.mainloop()
    return result["saved"]
