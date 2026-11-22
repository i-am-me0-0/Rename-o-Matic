import tkinter as tk
from typing import Optional, Sequence, Tuple


class EpisodeOffsetPrompt(tk.Toplevel):
    """Ask whether a season's proposed episode mapping should be offset."""

    def __init__(
        self,
        master,
        title: str,
        rows: Sequence[Tuple[int, int, str, str]],
    ):
        super().__init__(master)
        self.title("Check Episode Numbering")
        self.result: Optional[int] = None
        self.geometry("900x500")
        self.transient(master)
        self.grab_set()

        tk.Label(
            self,
            text=title,
            font=("Arial", 12, "bold"),
        ).pack(pady=(10, 4))
        tk.Label(
            self,
            text=(
                "A special or missing episode may be shifting the season. "
                "Review the proposed source episodes and choose an offset."
            ),
            wraplength=840,
            justify="left",
        ).pack(pady=(0, 8))

        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(frame)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas)
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        headers = ("Local", "Proposed source", "Title", "File")
        for column, header in enumerate(headers):
            tk.Label(
                content,
                text=header,
                font=("Arial", 9, "bold"),
                anchor="w",
            ).grid(row=0, column=column, sticky="w", padx=4, pady=(0, 4))

        for row_index, (local_ep, source_ep, title_text, file_name) in enumerate(rows, start=1):
            values = (
                f"E{local_ep:02}",
                f"E{source_ep:02}",
                title_text or "(title unavailable)",
                file_name,
            )
            for column, value in enumerate(values):
                tk.Label(content, text=value, anchor="w").grid(
                    row=row_index,
                    column=column,
                    sticky="w",
                    padx=4,
                    pady=2,
                )

        controls = tk.Frame(self)
        controls.pack(fill="x", padx=10, pady=10)
        tk.Label(controls, text="Offset:").pack(side="left")
        self.offset_var = tk.IntVar(value=1)
        tk.Spinbox(
            controls,
            from_=-10,
            to=10,
            textvariable=self.offset_var,
            width=5,
        ).pack(side="left", padx=(4, 12))
        tk.Button(controls, text="Apply Offset", command=self._apply).pack(side="left", padx=4)
        tk.Button(controls, text="Keep Current", command=self._keep).pack(side="left", padx=4)
        tk.Button(controls, text="Cancel", command=self._cancel).pack(side="right", padx=4)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _apply(self):
        try:
            self.result = int(self.offset_var.get())
        except (TypeError, ValueError):
            self.result = None
        self.destroy()

    def _keep(self):
        self.result = 0
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


def prompt_for_episode_offset(
    master,
    title: str,
    rows: Sequence[Tuple[int, int, str, str]],
) -> Optional[int]:
    prompt = EpisodeOffsetPrompt(master, title, rows)
    master.wait_window(prompt)
    return prompt.result
