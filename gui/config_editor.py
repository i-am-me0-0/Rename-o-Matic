# gui/config_editor.py
import tkinter as tk
from config import cfg, reload_config, CONFIG_FILE
from tkinter import messagebox

class ConfigEditorWindow(tk.Frame):
    def __init__(self, master, on_back, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.text = tk.Text(self, wrap="none", width=80, height=30)
        self.text.pack(fill="both", expand=True, padx=10, pady=10)

        self.btn_save = tk.Button(self, text="Save Config", command=self.save_config)
        self.btn_save.pack(pady=5)

        btn_back = tk.Button(self, text="Back", command=on_back)
        btn_back.pack(pady=10)

        self.load_config_text()
        self.on_back = on_back

    def load_config_text(self):
        """Load config.ini content as raw text into the text widget"""
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", content)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load config.ini: {e}")

    def save_config(self):
        """Save the edited text back to config.ini and reload"""
        content = self.text.get("1.0", tk.END)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            reload_config()
            messagebox.showinfo("Saved", "Config saved and reloaded.")
            if self.on_back:
                self.on_back()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config.ini: {e}")