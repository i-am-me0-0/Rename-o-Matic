# gui/scroll_utils.py
import platform

def bind_mousewheel_scrolling(canvas, widget=None, require_focus=False):
    """
    Cross-platform binding for mouse-wheel scrolling of a Canvas.

    - By default (require_focus=False) it will enable scrolling while the mouse is over the canvas.
      It does this by binding wheel handlers with bind_all when the mouse enters the canvas, and
      unbinding them on leave. This reliably captures wheel events even when child widgets exist.

    - If require_focus=True, scrolling will only happen when the keyboard focus is inside `widget`
      (or one of its descendants). In that mode you must pass `widget` (the parent widget to check).
    """
    system = platform.system()

    if require_focus and widget is None:
        raise ValueError("require_focus=True requires a widget argument")

    def _focus_inside():
        """Return True if keyboard focus is inside `widget` (or its descendants)."""
        if widget is None:
            return False
        focused = widget.focus_get()
        # widget names in Tkinter are hierarchical; descendants' string names start with parent's name
        return bool(focused) and str(focused).startswith(str(widget))

    def _should_handle():
        return _focus_inside() if require_focus else True

    def _on_mousewheel(event):
        if not _should_handle():
            return
        # Windows / macOS
        if system == "Windows":
            canvas.yview_scroll(-1 * int(event.delta / 120), "units")
        elif system == "Darwin":
            canvas.yview_scroll(-1 * int(event.delta), "units")

    def _on_linux_button(event):
        if not _should_handle():
            return
        # Button-4 = up, Button-5 = down
        if event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")

    def _bind_all_wheel(event=None):
        if system == "Linux":
            canvas.bind_all("<Button-4>", _on_linux_button)
            canvas.bind_all("<Button-5>", _on_linux_button)
        else:
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_all_wheel(event=None):
        if system == "Linux":
            try:
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass
        else:
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass

    # bind enter/leave on the canvas to (un)bind the global wheel handlers
    canvas.bind("<Enter>", _bind_all_wheel)
    canvas.bind("<Leave>", _unbind_all_wheel)

    # cleanup: unbind and detach enter/leave when canvas (or widget) destroyed
    def _cleanup(event=None):
        _unbind_all_wheel()
        try:
            canvas.unbind("<Enter>")
            canvas.unbind("<Leave>")
        except Exception:
            pass

    canvas.bind("<Destroy>", _cleanup)
    if widget is not None:
        try:
            widget.bind("<Destroy>", _cleanup)
        except Exception:
            pass

    # return cleanup for caller if they want to call it explicitly
    return _cleanup
