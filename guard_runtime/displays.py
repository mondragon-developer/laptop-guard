"""Windows monitor geometry using only the standard library."""
import ctypes
import sys
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Display:
    x: int
    y: int
    width: int
    height: int


def enable_dpi_awareness():
    """Call before creating Tk windows; keep geometry in physical pixels."""
    if sys.platform != "win32":
        return
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        function = user32.SetProcessDpiAwarenessContext
        function.argtypes = [ctypes.c_void_p]
        function.restype = wintypes.BOOL
        if not function(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            # Packaged Python may have a manifest fixing the process default.
            thread_context = user32.SetThreadDpiAwarenessContext
            thread_context.argtypes = [ctypes.c_void_p]
            thread_context.restype = ctypes.c_void_p
            thread_context(ctypes.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


def monitors(root):
    if sys.platform != "win32":
        return (Display(0, 0, root.winfo_screenwidth(), root.winfo_screenheight()),)
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE,
                                      wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                      wintypes.LPARAM)
    found = []

    @callback_type
    def collect(handle, dc, rectangle, data):
        rect = rectangle.contents
        if rect.right > rect.left and rect.bottom > rect.top:
            found.append(Display(rect.left, rect.top, rect.right - rect.left,
                                 rect.bottom - rect.top))
        return True

    enumerate_monitors = user32.EnumDisplayMonitors
    enumerate_monitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                  callback_type, wintypes.LPARAM]
    enumerate_monitors.restype = wintypes.BOOL
    if not enumerate_monitors(None, None, collect, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not found:
        raise RuntimeError("Windows reported no attached displays")
    return tuple(sorted(set(found)))


def place(window, display):
    """Use signed desktop coordinates, including monitors left/above primary."""
    if sys.platform != "win32":
        window.attributes("-fullscreen", True)
        return
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    window.update_idletasks()
    get_ancestor = user32.GetAncestor
    get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
    get_ancestor.restype = wintypes.HWND
    handle = get_ancestor(window.winfo_id(), 2)  # Tk's outer top-level HWND
    set_position = user32.SetWindowPos
    set_position.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    set_position.restype = wintypes.BOOL
    if not set_position(handle, ctypes.c_void_p(-1), display.x, display.y,
                        display.width, display.height, 0x0010 | 0x0040):
        raise ctypes.WinError(ctypes.get_last_error())
