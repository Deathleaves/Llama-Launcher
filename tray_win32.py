"""
tray_win32.py — Win32 System Tray Icon (zero tkinter dependency)

Extracted from llama_gui.py. Provides a native Windows system tray icon
using ctypes/Win32 API, suitable for use with asyncio-based applications.

Usage:
    tray = WinTrayIcon(
        tooltip="Llama Server - Stopped",
        on_show=show_callback,       # e.g. open browser
        on_exit=exit_callback,       # e.g. shutdown app
        on_start=start_callback,     # e.g. start server
        on_stop=stop_callback,       # e.g. stop server
    )
    tray.start()   # starts background message loop thread
    ...
    tray.stop()    # removes icon and stops thread
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import struct
import threading
import time
import uuid
from typing import Callable

# ── Win32 Constants ──────────────────────────────────────────

WM_USER = 0x0400
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_GUID = 0x00000020
WS_OVERLAPPED = 0x00000000
COLOR_WINDOW = 5
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

# Menu command IDs
IDM_OPEN_WEB = 1001
IDM_START_SVR = 1002
IDM_STOP_SVR = 1003
IDM_SEPARATOR = 0
IDM_EXIT = 1009

# Unique GUID for this application's tray icon
TRAY_GUID = "{B6F7C8A9-1D2E-4F3A-5B6C-7D8E9F0A1B2C}"


# ── Win32 Structures ─────────────────────────────────────────

class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hWnd", ctypes.wintypes.HWND),
        ("uID", ctypes.wintypes.UINT),
        ("uFlags", ctypes.wintypes.UINT),
        ("uCallbackMessage", ctypes.wintypes.UINT),
        ("hIcon", ctypes.wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.wintypes.DWORD),
        ("dwStateMask", ctypes.wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", ctypes.wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.wintypes.DWORD),
        ("guidItem", ctypes.c_char * 16),
        ("hBalloonIcon", ctypes.wintypes.HICON),
    ]


WNDPROC_TYPE = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, ctypes.wintypes.HWND,
    ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)


class WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("style", ctypes.wintypes.UINT),
        ("lpfnWndProc", WNDPROC_TYPE),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HCURSOR),
        ("hbrBackground", ctypes.wintypes.HBRUSH),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
        ("hIconSm", ctypes.wintypes.HICON),
    ]


# Fix DefWindowProcW argtypes for 64-bit
ctypes.windll.user32.DefWindowProcW.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
ctypes.windll.user32.DefWindowProcW.restype = ctypes.c_longlong


# ── Icon Generation (no Pillow dependency) ──────────────────

def _make_default_icon() -> int:
    """Get the default application icon (HICON)."""
    return ctypes.windll.user32.LoadIconW(0, ctypes.c_void_p(32512))  # IDI_APPLICATION


def _make_popup_menu(hwnd: int, server_running: bool) -> int:
    """Create and display a popup menu. Returns selected command ID or 0."""
    pt = struct.pack("ii", 0, 0)
    ctypes.windll.user32.GetCursorPos(pt)
    x, y = struct.unpack("ii", pt)

    ctypes.windll.user32.SetForegroundWindow(hwnd)

    hmenu = ctypes.windll.user32.CreatePopupMenu()
    ctypes.windll.user32.AppendMenuW(hmenu, 0x00000000, IDM_OPEN_WEB, "Open Web UI")
    ctypes.windll.user32.AppendMenuW(hmenu, 0x00000800, IDM_SEPARATOR, "")
    if server_running:
        ctypes.windll.user32.AppendMenuW(hmenu, 0x00000000, IDM_STOP_SVR, "Stop Server")
    else:
        ctypes.windll.user32.AppendMenuW(hmenu, 0x00000000, IDM_START_SVR, "Start Server")
    ctypes.windll.user32.AppendMenuW(hmenu, 0x00000800, IDM_SEPARATOR, "")
    ctypes.windll.user32.AppendMenuW(hmenu, 0x00000000, IDM_EXIT, "Exit")

    flags = TPM_RIGHTBUTTON | TPM_RETURNCMD | 0x0020  # TPM_BOTTOMALIGN
    cmd = ctypes.windll.user32.TrackPopupMenu(hmenu, flags, x, y, 0, hwnd, None)
    ctypes.windll.user32.PostMessageW(hwnd, 0, 0, 0)
    ctypes.windll.user32.DestroyMenu(hmenu)
    return cmd


# ── Per-instance dispatch ────────────────────────────────────

_tray_instances: dict[int, "WinTrayIcon"] = {}


@WNDPROC_TYPE
def _global_wnd_proc(hwnd, msg, wparam, lparam):
    """Global window procedure — dispatches to the right WinTrayIcon."""
    inst = _tray_instances.get(hwnd)
    if inst:
        return inst._handle_msg(hwnd, msg, wparam, lparam)
    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


# ── WinTrayIcon ──────────────────────────────────────────────

class WinTrayIcon:
    """Minimal Windows system tray icon using ctypes/Win32 API.

    Callbacks are invoked from a background thread. Use thread-safe
    patterns (e.g. asyncio.run_coroutine_threadsafe) to communicate
    back to the main event loop.
    """

    def __init__(
        self,
        tooltip: str,
        on_show: Callable[[], None],
        on_exit: Callable[[], None],
        on_start: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
    ):
        self._on_show = on_show
        self._on_exit = on_exit
        self._on_start = on_start
        self._on_stop = on_stop
        self._tooltip = tooltip
        self._hwnd = None
        self._hicon = _make_default_icon()
        self._running = False
        self._thread = None
        self._icon_added = False
        self._server_running = False

    def start(self) -> None:
        """Start the tray icon in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=False)
        self._thread.start()
        # Wait for window creation
        for _ in range(200):
            if self._hwnd:
                break
            time.sleep(0.01)

    def stop(self) -> None:
        """Remove tray icon and stop the message loop."""
        self._running = False
        hwnd = self._hwnd
        if hwnd:
            self._remove_icon()
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def update_tooltip(self, tooltip: str) -> None:
        """Update the tray icon tooltip."""
        self._tooltip = tooltip
        if self._hwnd:
            self._modify_icon()

    def set_server_running(self, running: bool) -> None:
        """Update internal server state (affects right-click menu)."""
        self._server_running = running

    def _handle_msg(self, hwnd, msg, wparam, lparam):
        """Handle a window message."""
        imsg = int(msg)
        ilparam = int(lparam)

        if imsg == WM_TRAY:
            try:
                if ilparam == WM_LBUTTONUP:
                    self._on_show()
                elif ilparam == WM_RBUTTONUP:
                    cmd = _make_popup_menu(hwnd, self._server_running)
                    if cmd == IDM_OPEN_WEB:
                        self._on_show()
                    elif cmd == IDM_START_SVR and self._on_start:
                        self._on_start()
                    elif cmd == IDM_STOP_SVR and self._on_stop:
                        self._on_stop()
                    elif cmd == IDM_EXIT:
                        self._on_exit()
            except Exception:
                import traceback
                traceback.print_exc()
            return 0
        elif imsg == WM_CLOSE:
            ctypes.windll.user32.DestroyWindow(hwnd)
            return 0
        elif imsg == WM_DESTROY:
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _message_loop(self) -> None:
        """Create a hidden window and run the message loop."""
        hinst = ctypes.windll.kernel32.GetModuleHandleW(None)

        wnd_class = WNDCLASSEX()
        wnd_class.cbSize = ctypes.sizeof(WNDCLASSEX)
        wnd_class.style = 0
        wnd_class.lpfnWndProc = _global_wnd_proc  # type: ignore[assignment]
        wnd_class.cbClsExtra = 0
        wnd_class.cbWndExtra = 0
        wnd_class.hInstance = hinst
        wnd_class.hIcon = self._hicon or 0
        wnd_class.hCursor = 0
        wnd_class.hbrBackground = ctypes.wintypes.HBRUSH(COLOR_WINDOW + 1)
        wnd_class.lpszMenuName = 0
        wnd_class.lpszClassName = "LlamaLauncherTray"
        wnd_class.hIconSm = self._hicon or 0

        atom = ctypes.windll.user32.RegisterClassExW(ctypes.byref(wnd_class))
        if not atom:
            return

        hwnd = ctypes.windll.user32.CreateWindowExW(
            0, "LlamaLauncherTray", "", WS_OVERLAPPED,
            0, 0, 0, 0, 0, 0, hinst, 0)

        if not hwnd:
            ctypes.windll.user32.UnregisterClassW("LlamaLauncherTray", hinst)
            return

        self._hwnd = hwnd
        _tray_instances[hwnd] = self

        try:
            self._add_icon()
        except Exception:
            pass

        msg = ctypes.wintypes.MSG()
        while self._running:
            if ctypes.windll.user32.PeekMessageW(
                    ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE
                if msg.message == 0x0012:  # WM_QUIT
                    break
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.05)

        _tray_instances.pop(hwnd, None)
        self._remove_icon()
        ctypes.windll.user32.UnregisterClassW("LlamaLauncherTray", hinst)
        self._hwnd = None
        if self._hicon:
            ctypes.windll.user32.DestroyIcon(self._hicon)
            self._hicon = None

    def _add_icon(self) -> None:
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP | NIF_GUID
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = self._tooltip
        guid_bytes = uuid.UUID(TRAY_GUID).bytes_le
        ctypes.memmove(nid.guidItem, guid_bytes, 16)
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._icon_added = True

    def _modify_icon(self) -> None:
        if not self._hwnd:
            return
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_TIP
        nid.szTip = self._tooltip
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _remove_icon(self) -> None:
        if not self._hwnd or not self._icon_added:
            return
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self._hwnd
        nid.uID = 1
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        self._icon_added = False
