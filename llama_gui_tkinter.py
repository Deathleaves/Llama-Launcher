"""
llama_gui.py — Llama Server Launcher

Windows desktop GUI for managing llama.cpp inference server.
Features: visual config, real-time color-coded logs, system tray, hardware monitoring.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import queue
import re
import struct
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import psutil
from PIL import Image, ImageDraw

from config import AppConfig

# ── Win32 Tray Icon (replaces pystray) ──────────────────────

# Win32 constants
WM_USER = 0x0400
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_STATE = 0x00000008
NIF_INFO = 0x00000010
NIF_GUID = 0x00000020
NIS_HIDDEN = 0x00000001
NIS_SHAREDICON = 0x00000002
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
WS_OVERLAPPED = 0x00000000
WS_POPUP = 0x80000000
CW_USEDEFAULT = 0x80000000
IDI_APPLICATION = 32512
WM_CREATE = 0x0001
SW_HIDE = 0
SW_SHOW = 5
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
HWND_MESSAGE = -3
COLOR_WINDOW = 5

# Menu command IDs
IDM_SHOW = 1001
IDM_EXIT = 1002

# GUID for the tray icon (unique per app)
TRAY_GUID = "{B6F7C8A9-1D2E-4F3A-5B6C-7D8E9F0A1B2C}"

# Win32 structures
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

# Forward declaration — WNDPROC_TYPE needed before WNDCLASSEX
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


def _pil_to_hicon(im: Image.Image) -> int:
    """Convert a PIL Image to a Win32 HICON using CreateIconIndirect."""
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    w, h = im.size

    # Create color bitmap
    hdc = ctypes.windll.user32.GetDC(0)
    hbm_color = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, w, h)

    # BITMAPINFO for 32bpp BGRA
    buf = struct.pack("IiiHHIIiiII", 40, w, h, 1, 32, 0, w * h * 4, 0, 0, 0, 0)
    pixels = im.tobytes("raw", "BGRA")
    ctypes.windll.gdi32.SetDIBits(hdc, hbm_color, 0, h, pixels,
        ctypes.c_char_p(buf), 0)

    # Create mask bitmap (all 1s = fully opaque)
    hbm_mask = ctypes.windll.gdi32.CreateBitmap(w, h, 1, 1, None)

    # ICONINFO
    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", ctypes.wintypes.BOOL),
            ("xHotspot", ctypes.wintypes.DWORD),
            ("yHotspot", ctypes.wintypes.DWORD),
            ("hbmMask", ctypes.wintypes.HBITMAP),
            ("hbmColor", ctypes.wintypes.HBITMAP),
        ]
    ii = ICONINFO()
    ii.fIcon = True
    ii.xHotspot = 0
    ii.yHotspot = 0
    ii.hbmMask = hbm_mask
    ii.hbmColor = hbm_color

    hicon = ctypes.windll.user32.CreateIconIndirect(ctypes.byref(ii))

    ctypes.windll.gdi32.DeleteObject(hbm_color)
    ctypes.windll.gdi32.DeleteObject(hbm_mask)
    ctypes.windll.user32.ReleaseDC(0, hdc)
    return hicon


def _make_tray_icon_image() -> Image.Image:
    """Generate a 32x32 tray icon."""
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 30, 30], fill=(49, 50, 68))
    draw.ellipse([3, 3, 29, 29], fill=(30, 30, 46))
    draw.rectangle([10, 6, 14, 24], fill=(203, 166, 247))
    draw.rectangle([10, 20, 22, 24], fill=(203, 166, 247))
    return img


# Instance registry for global window procedure dispatch
_tray_instances: dict[int, "WinTrayIcon"] = {}

# Fix DefWindowProcW argtypes for 64-bit
ctypes.windll.user32.DefWindowProcW.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
ctypes.windll.user32.DefWindowProcW.restype = ctypes.c_longlong

@WNDPROC_TYPE
def _global_wnd_proc(hwnd, msg, wparam, lparam):
    """Global window procedure — dispatches to the right WinTrayIcon instance."""
    inst = _tray_instances.get(hwnd)
    if inst:
        return inst._handle_msg(hwnd, msg, wparam, lparam)
    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _make_popup_menu(hwnd: int) -> int:
    """Create and display a popup menu. Returns selected command ID or 0."""
    # Get cursor position
    pt = struct.pack("ii", 0, 0)
    ctypes.windll.user32.GetCursorPos(pt)
    x, y = struct.unpack("ii", pt)

    # Must bring our window to foreground so TrackPopupMenu can detect
    # click-away events and dismiss the menu properly.
    ctypes.windll.user32.SetForegroundWindow(hwnd)

    hmenu = ctypes.windll.user32.CreatePopupMenu()
    ctypes.windll.user32.AppendMenuW(hmenu, 0x00000000, IDM_SHOW, "Show Window")
    ctypes.windll.user32.AppendMenuW(hmenu, 0x00000800, 0, "")  # separator
    ctypes.windll.user32.AppendMenuW(hmenu, 0x00000000, IDM_EXIT, "Exit")

    # TPM_RIGHTBUTTON: menu tracks right mouse button
    # TPM_RETURNCMD:   returns menu item id instead of sending WM_COMMAND
    # TPM_BOTTOMALIGN: menu aligns below the click point
    flags = TPM_RIGHTBUTTON | TPM_RETURNCMD | 0x0020  # TPM_BOTTOMALIGN
    cmd = ctypes.windll.user32.TrackPopupMenu(hmenu, flags, x, y, 0, hwnd, None)

    # Standard pattern for tray popup menu: post a benign message so the
    # window can properly handle deactivation after the menu closes.
    ctypes.windll.user32.PostMessageW(hwnd, 0, 0, 0)

    ctypes.windll.user32.DestroyMenu(hmenu)
    return cmd


class WinTrayIcon:
    """Minimal Windows system tray icon using ctypes/Win32 API."""

    def __init__(self, tooltip: str, on_show, on_exit):
        self._on_show = on_show
        self._on_exit = on_exit
        self._tooltip = tooltip
        self._hwnd = None
        self._hicon = _pil_to_hicon(_make_tray_icon_image())
        self._running = False
        self._thread = None
        self._icon_added = False  # guard against double removal

    def start(self) -> None:
        """Start the tray icon in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=False)
        self._thread.start()
        # Wait for window to be created
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

    def _handle_msg(self, hwnd, msg, wparam, lparam):
        """Handle a window message. Called from global wnd proc via ctypes."""
        # Cast to int for safe comparison
        imsg = int(msg)
        iwparam = int(wparam)
        ilparam = int(lparam)

        if imsg == WM_TRAY:
            try:
                if ilparam == WM_LBUTTONUP:
                    self._on_show()
                elif ilparam == WM_RBUTTONUP:
                    cmd = _make_popup_menu(hwnd)
                    if cmd == IDM_SHOW:
                        self._on_show()
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
        """Create a message-only window and run the message loop."""
        hinst = ctypes.windll.kernel32.GetModuleHandleW(None)

        # Register window class using global WNDPROC
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

        # Create a hidden (not message-only) window so it can receive
        # foreground activation when showing the popup context menu.
        # Message-only windows (HWND_MESSAGE) cannot be made foreground,
        # which breaks TrackPopupMenu click-away dismissal.
        hwnd = ctypes.windll.user32.CreateWindowExW(
            0, "LlamaLauncherTray", "", WS_OVERLAPPED,
            0, 0, 0, 0, 0, 0, hinst, 0)

        if not hwnd:
            ctypes.windll.user32.UnregisterClassW("LlamaLauncherTray", hinst)
            return

        self._hwnd = hwnd
        # Register this instance so _global_wnd_proc can dispatch to it
        _tray_instances[hwnd] = self

        # Add tray icon
        try:
            self._add_icon()
        except Exception as e:
            # If adding icon fails, still run message loop for cleanup
            pass

        # Message loop
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

        # Cleanup
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
        # Set GUID (16 bytes raw)
        import uuid
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

# ── Constants ──────────────────────────────────────────────

# Catppuccin Mocha color palette
COLORS = {
    "base":       "#1e1e2e",
    "mantle":     "#181825",
    "crust":      "#11111b",
    "surface0":   "#313244",
    "surface1":   "#45475a",
    "surface2":   "#585b70",
    "text":       "#cdd6f4",
    "subtext0":   "#a6adc8",
    "subtext1":   "#bac2de",
    "lavender":   "#cba6f7",   # System
    "red":        "#f38ba8",   # Error
    "peach":      "#fab387",   # Warn
    "blue":       "#89b4fa",   # Proxy
    "green":      "#a6e3a1",   # Info
    "teal":       "#94e2d5",
    "yellow":     "#f9e2af",
}

LOG_TAGS: dict[str, dict[str, str]] = {
    "system":  {"foreground": COLORS["lavender"], "label": "SYS"},
    "error":   {"foreground": COLORS["red"],      "label": "ERR"},
    "warn":    {"foreground": COLORS["peach"],    "label": "WRN"},
    "proxy":   {"foreground": COLORS["blue"],     "label": "PRX"},
    "info":    {"foreground": COLORS["green"],    "label": "INF"},
    "cmd":     {"foreground": COLORS["teal"],     "label": "CMD"},
}

LOGO_ASCII = r"""
╔══════════════════════════════════════════════════╗
║  ██╗     ██╗      █████╗ ███╗   ███╗ █████╗    ║
║  ██║     ██║     ██╔══██╗████╗ ████║██╔══██╗   ║
║  ██║     ██║     ███████║██╔████╔██║███████║   ║
║  ██║     ██║     ██╔══██║██║╚██╔╝██║██╔══██║   ║
║  ███████╗███████╗██║  ██║██║ ╚═╝ ██║██║  ██║   ║
║  ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝   ║
║               LLAMA LAUNCHER                     ║
╚══════════════════════════════════════════════════╝
"""

APP_TITLE = "Llama Server Launcher"

# ── Main Application Class ─────────────────────────────────

class LlamaLauncher(tk.Tk):
    """Main GUI application for managing llama.cpp server."""

    def __init__(self) -> None:
        super().__init__()

        # ── Core state ──
        self.config: AppConfig = AppConfig()
        self.config_path = os.path.join(os.path.dirname(__file__), "llama_config.json")
        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue = queue.Queue()
        self.tray_icon = None
        self._poll_id: str | None = None
        self._monitor_id: str | None = None

        # ── Window setup ──
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1000, 600)
        self.configure(bg=COLORS["base"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Build UI ──
        self._setup_theme()
        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

        # ── Load config ──
        self._load_config_to_ui()

        # ── Start hardware monitor ──
        self._update_hardware_stats()

        # ── Create tray icon at startup ──
        self.after(500, self._create_tray_icon)

        # ── Thread-safe tray → main-thread dispatch ──
        self._tray_action_queue: queue.Queue = queue.Queue()
        self._poll_tray_actions()

        # ── Bindings ──
        self.bind("<Control-s>", lambda _e: self._save_config())

    # ═══════════════════════════════════════════════════════
    # Theme
    # ═══════════════════════════════════════════════════════

    def _setup_theme(self) -> None:
        """Configure ttk theme with dark Catppuccin Mocha colors."""
        style = ttk.Style(self)
        style.theme_use("clam")

        # Scoped color mapping: clam uses custom names prefixed with area
        style.configure(".", background=COLORS["base"], foreground=COLORS["text"],
                        fieldbackground=COLORS["surface0"], borderwidth=0)

        # TFrame
        style.configure("TFrame", background=COLORS["base"])
        style.configure("Surface.TFrame", background=COLORS["surface0"])
        style.configure("Toolbar.TFrame", background=COLORS["crust"])

        # TLabel
        style.configure("TLabel", background=COLORS["base"], foreground=COLORS["text"])
        style.configure("Toolbar.TLabel", background=COLORS["crust"], foreground=COLORS["text"],
                        font=("Segoe UI", 11, "bold"))
        style.configure("Status.TLabel", background=COLORS["mantle"], foreground=COLORS["subtext0"],
                        font=("Consolas", 9))
        style.configure("StatusActive.TLabel", background=COLORS["mantle"], foreground=COLORS["green"],
                        font=("Consolas", 9, "bold"))
        style.configure("ConfigLabel.TLabel", background=COLORS["surface0"],
                        foreground=COLORS["subtext1"], font=("Segoe UI", 9),
                        anchor="e", padding=(0, 0, 8, 0))

        # TLabelframe
        style.configure("Card.TLabelframe", background=COLORS["surface0"],
                        bordercolor=COLORS["surface1"], relief="solid",
                        borderwidth=1, padding=12)
        style.configure("Card.TLabelframe.Label", background=COLORS["surface0"],
                        foreground=COLORS["text"], font=("Segoe UI", 10, "bold"),
                        padding=(8, 4))

        # TButton
        style.configure("TButton", background=COLORS["surface1"], foreground=COLORS["text"],
                        borderwidth=0, padding=(12, 6), font=("Segoe UI", 9))
        style.map("TButton",
                  background=[("active", COLORS["surface2"]), ("disabled", COLORS["surface0"])],
                  foreground=[("disabled", COLORS["subtext0"])])
        style.configure("Primary.TButton", background=COLORS["green"], foreground=COLORS["base"],
                        font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton", background=[("active", COLORS["teal"])])
        style.configure("Danger.TButton", background=COLORS["red"], foreground=COLORS["base"],
                        font=("Segoe UI", 9, "bold"))
        style.map("Danger.TButton", background=[("active", "#e06c75")])
        style.configure("Toolbar.TButton", background=COLORS["surface1"], foreground=COLORS["text"],
                        padding=(10, 2), font=("Segoe UI", 9))
        style.map("Toolbar.TButton", background=[("active", COLORS["surface2"])])

        # TEntry
        style.configure("TEntry", fieldbackground=COLORS["surface0"], foreground=COLORS["text"],
                        insertcolor=COLORS["text"], padding=6)

        # TCombobox
        style.configure("TCombobox", fieldbackground=COLORS["surface0"], foreground=COLORS["text"],
                        background=COLORS["surface1"], arrowcolor=COLORS["text"],
                        selectbackground=COLORS["surface2"], selectforeground=COLORS["text"])
        self.option_add("*TCombobox*Listbox.background", COLORS["surface0"])
        self.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", COLORS["surface2"])
        self.option_add("*TCombobox*Listbox.selectForeground", COLORS["text"])

        # TSpinbox
        style.configure("TSpinbox", fieldbackground=COLORS["surface0"], foreground=COLORS["text"],
                        background=COLORS["surface1"], arrowcolor=COLORS["text"],
                        selectbackground=COLORS["surface2"], selectforeground=COLORS["text"],
                        padding=6)

        # TCheckbutton
        style.configure("TCheckbutton", background=COLORS["surface0"], foreground=COLORS["text"])
        style.map("TCheckbutton", background=[("active", COLORS["surface0"])])

        # TPanedwindow
        style.configure("TPanedwindow", background=COLORS["surface1"])

        # TScrollbar
        style.configure("TScrollbar", background=COLORS["surface1"],
                        troughcolor=COLORS["surface0"], arrowcolor=COLORS["text"])
        style.map("TScrollbar", background=[("active", COLORS["surface2"])])

        # TSeparator
        style.configure("TSeparator", background=COLORS["surface1"])

        # Sizegrip
        style.configure("TSizegrip", background=COLORS["mantle"])

    # ═══════════════════════════════════════════════════════
    # Toolbar
    # ═══════════════════════════════════════════════════════

    def _build_toolbar(self) -> None:
        """Top toolbar with title and tray button."""
        bar = ttk.Frame(self, style="Toolbar.TFrame", padding=(16, 6))
        bar.pack(fill=tk.X)

        ttk.Label(bar, text="🦙  " + APP_TITLE, style="Toolbar.TLabel").pack(side=tk.LEFT)

        self._tray_btn = ttk.Button(bar, text="Hide to Tray", style="Toolbar.TButton",
                                     command=self._hide_to_tray)
        self._tray_btn.pack(side=tk.RIGHT)

        self._server_status_led = tk.Canvas(bar, width=10, height=10,
                                            bg=COLORS["crust"], highlightthickness=0)
        self._server_status_led.pack(side=tk.RIGHT, padx=(0, 8))
        self._led_dot = self._server_status_led.create_oval(0, 0, 10, 10, fill=COLORS["red"], outline="")

    # ═══════════════════════════════════════════════════════
    # Main Content Area
    # ═══════════════════════════════════════════════════════

    def _build_main_area(self) -> None:
        """Build the left (config) / right (log) split layout."""
        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=(12, 12), pady=(8, 4))

        self._build_config_panel(pane)
        self._build_log_panel(pane)

        # Weight 50/50
        pane.update_idletasks()
        pane.sashpos(0, 650)

    # ── Config Panel (Left) ──────────────────────────────

    def _build_config_panel(self, parent: ttk.PanedWindow) -> None:
        """Scrollable configuration panel on the left side."""
        outer = ttk.Frame(parent)
        parent.add(outer, weight=1)

        # Canvas + Scrollbar for scrolling
        canvas = tk.Canvas(outer, bg=COLORS["base"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        self._config_canvas = canvas

        scroll_frame = ttk.Frame(canvas, style="TFrame")
        self._config_scroll_frame = scroll_frame

        # Debounced scroll-region update — only on idle, not during active resize
        self._scroll_region_id = None
        def _schedule_scroll_region(_event=None):
            if self._scroll_region_id is not None:
                return  # already queued
            self._scroll_region_id = canvas.after_idle(self._update_scroll_region)
        scroll_frame.bind("<Configure>", _schedule_scroll_region, add="+")

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", tags="inner")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        # Inner-width sync on idle only (never during active drag/resize)
        self._width_sync_id = None
        def _schedule_width_sync(_event):
            if self._width_sync_id is not None:
                self.after_cancel(self._width_sync_id)
            self._width_sync_id = self.after_idle(
                self._sync_inner_width
            )
        canvas.bind("<Configure>", _schedule_width_sync, add="+")

        content = ttk.Frame(scroll_frame, style="TFrame", padding=(4, 4))
        content.pack(fill=tk.BOTH, expand=True)

        # ── Section: File Paths ──
        paths_frame = ttk.Labelframe(content, text="  File Paths  ", style="Card.TLabelframe")
        paths_frame.pack(fill=tk.X, pady=(0, 10))
        self._path_entries: dict[str, tk.StringVar] = {}

        self._create_path_row(paths_frame, "Server Path", "server_path",
                              "llama-server.exe")
        self._create_path_row(paths_frame, "Model Path", "model_path",
                              "GGUF Files", "*.gguf")
        self._create_path_row(paths_frame, "Vision MMProj", "mmproj_path",
                              "GGUF Files", "*.gguf")

        # ── Section: Performance ──
        perf_frame = ttk.Labelframe(content, text="  Performance  ", style="Card.TLabelframe")
        perf_frame.pack(fill=tk.X, pady=(0, 10))
        self._spin_vars: dict[str, tk.StringVar] = {}

        self._create_spinbox_row(perf_frame, "Threads", "threads", 1, 256)
        self._create_spinbox_row(perf_frame, "Batch Size", "batch_size", 1, 32768)
        self._create_spinbox_row(perf_frame, "GPU Layers", "gpu_layers", 0, 999)
        self._create_spinbox_row(perf_frame, "Context Length", "context_length", 256, 1048576)

        # ── Section: Server ──
        srv_frame = ttk.Labelframe(content, text="  Server  ", style="Card.TLabelframe")
        srv_frame.pack(fill=tk.X, pady=(0, 10))

        self._create_spinbox_row(srv_frame, "Port", "port", 1024, 65535)
        self._create_entry_row(srv_frame, "Temperature", "temperature")
        self._create_entry_row(srv_frame, "Model Alias", "model_alias")
        self._create_combo_row(srv_frame, "Chat Template", "chat_template",
                               list(AppConfig.CHAT_TEMPLATES))
        self._create_combo_row(srv_frame, "Log Level", "log_level",
                               list(AppConfig.LOG_LEVELS))
        self._create_check_row(srv_frame, "Flash Attention", "flash_attn")
        self._create_check_row(srv_frame, "Lock Memory (mlock)", "mlock")

        # ── Buttons ──
        btn_area = ttk.Frame(content, style="TFrame", padding=(0, 8))
        btn_area.pack(fill=tk.X)

        self._save_btn = ttk.Button(btn_area, text="💾  Save Config",
                                     command=self._save_config)
        self._save_btn.pack(fill=tk.X, pady=(0, 4))

        self._start_stop_btn = ttk.Button(btn_area, text="▶  Start Server",
                                           style="Primary.TButton",
                                           command=self._start_server)
        self._start_stop_btn.pack(fill=tk.X, pady=(0, 4))

        self._clear_btn = ttk.Button(btn_area, text="🗑  Clear Log",
                                      command=self._clear_log)
        self._clear_btn.pack(fill=tk.X)

        # Keep references for sizing
        self._config_content = content
        self._canvas_outer = outer

    # ── Widget factory methods ───────────────────────────

    def _create_path_row(self, parent: ttk.Frame, label: str,
                         config_key: str, title: str,
                         filetypes: str = "All Files", ext: str = "*") -> None:
        """Create a Label | Entry | Browse row for file paths."""
        row = ttk.Frame(parent, style="TFrame", padding=(0, 2))
        row.pack(fill=tk.X, padx=4, pady=1)

        lbl = ttk.Label(row, text=label, style="ConfigLabel.TLabel", width=16)
        lbl.pack(side=tk.LEFT)

        var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        btn = ttk.Button(row, text="Browse", width=8,
                         command=lambda: self._browse_file(var, title, filetypes, ext))
        btn.pack(side=tk.RIGHT)

        self._path_entries[config_key] = var

    def _create_spinbox_row(self, parent: ttk.Frame, label: str,
                            config_key: str, from_: int, to: int) -> None:
        """Create a Label | Spinbox row for numeric input."""
        row = ttk.Frame(parent, style="TFrame", padding=(0, 2))
        row.pack(fill=tk.X, padx=4, pady=1)

        lbl = ttk.Label(row, text=label, style="ConfigLabel.TLabel", width=16)
        lbl.pack(side=tk.LEFT)

        var = tk.StringVar()
        sb = ttk.Spinbox(row, textvariable=var, from_=from_, to=to, width=10)
        sb.pack(side=tk.LEFT, padx=(0, 8))

        self._spin_vars[config_key] = var

    def _create_entry_row(self, parent: ttk.Frame, label: str,
                          config_key: str) -> None:
        """Create a Label | Entry row for free text input."""
        row = ttk.Frame(parent, style="TFrame", padding=(0, 2))
        row.pack(fill=tk.X, padx=4, pady=1)

        lbl = ttk.Label(row, text=label, style="ConfigLabel.TLabel", width=16)
        lbl.pack(side=tk.LEFT)

        var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self._spin_vars[config_key] = var  # Reuse dict for entry vars too

    def _create_combo_row(self, parent: ttk.Frame, label: str,
                          config_key: str, values: list[str]) -> None:
        """Create a Label | Combobox row."""
        row = ttk.Frame(parent, style="TFrame", padding=(0, 2))
        row.pack(fill=tk.X, padx=4, pady=1)

        lbl = ttk.Label(row, text=label, style="ConfigLabel.TLabel", width=16)
        lbl.pack(side=tk.LEFT)

        var = tk.StringVar()
        combo = ttk.Combobox(row, textvariable=var, values=values,
                             state="readonly", width=12)
        combo.pack(side=tk.LEFT, padx=(0, 8))

        self._spin_vars[config_key] = var

    def _create_check_row(self, parent: ttk.Frame, label: str,
                          config_key: str) -> None:
        """Create a Label | Checkbutton row."""
        row = ttk.Frame(parent, style="TFrame", padding=(0, 2))
        row.pack(fill=tk.X, padx=4, pady=1)

        lbl = ttk.Label(row, text=label, style="ConfigLabel.TLabel", width=16)
        lbl.pack(side=tk.LEFT)

        var = tk.BooleanVar()
        cb = ttk.Checkbutton(row, variable=var)
        cb.pack(side=tk.LEFT)

        self._spin_vars[config_key] = var  # Reuse dict for bool vars

    def _update_scroll_region(self) -> None:
        """Update the canvas scroll region. Called via after_idle."""
        self._scroll_region_id = None
        try:
            self._config_canvas.configure(
                scrollregion=self._config_canvas.bbox("all"))
        except Exception:
            pass

    def _sync_inner_width(self) -> None:
        """Sync inner frame width to canvas width. Called via after_idle."""
        self._width_sync_id = None
        try:
            w = self._config_canvas.winfo_width()
            if w > 1:
                self._config_canvas.itemconfig("inner", width=w)
        except Exception:
            pass

    # ── Browse helper ─────────────────────────────────────

    def _browse_file(self, var: tk.StringVar, title: str,
                     filetypes_label: str, ext: str) -> None:
        """Open a file dialog and set the StringVar to the selected path."""
        filetypes = [(filetypes_label, ext), ("All Files", "*")]
        initial = var.get()
        initial_dir = os.path.dirname(initial) if initial else os.path.expanduser("~")
        path = filedialog.askopenfilename(title=title, filetypes=filetypes,
                                          initialdir=initial_dir)
        if path:
            var.set(path)

    # ═══════════════════════════════════════════════════════
    # Log Panel (Right)
    # ═══════════════════════════════════════════════════════

    def _build_log_panel(self, parent: ttk.PanedWindow) -> None:
        """Dark-themed log output panel on the right side."""
        outer = ttk.Frame(parent)
        parent.add(outer, weight=1)

        # Toolbar
        log_bar = ttk.Frame(outer, style="TFrame", padding=(0, 0, 0, 2))
        log_bar.pack(fill=tk.X)

        ttk.Label(log_bar, text="  Server Log", style="ConfigLabel.TLabel",
                  background=COLORS["base"], anchor="w").pack(side=tk.LEFT)

        ttk.Button(log_bar, text="Clear Log", style="Toolbar.TButton",
                   command=self._clear_log).pack(side=tk.RIGHT, padx=(0, 4))

        # ScrolledText for log output
        self._log_text = scrolledtext.ScrolledText(
            outer,
            bg=COLORS["mantle"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["surface2"],
            selectforeground=COLORS["text"],
            font=("Consolas", 9),
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            padx=8,
            pady=6,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True)

        # Configure color tags
        for tag_name, tag_info in LOG_TAGS.items():
            self._log_text.tag_config(
                tag_name,
                foreground=tag_info["foreground"],
                font=("Consolas", 9, "bold"),
            )
        # Dim tag for ANSI-filtered content
        self._log_text.tag_config("dim", foreground=COLORS["subtext0"])

        # Make read-only but allow text insertion
        self._log_text.bind("<Key>", lambda e: "break")

    # ═══════════════════════════════════════════════════════
    # Status Bar
    # ═══════════════════════════════════════════════════════

    def _build_status_bar(self) -> None:
        """Bottom status bar with server state and hardware stats."""
        bar = ttk.Frame(self, style="Surface.TFrame", padding=(12, 4))
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_label = ttk.Label(bar, text="●  Server: Stopped",
                                       style="Status.TLabel")
        self._status_label.pack(side=tk.LEFT)

        self._cpu_label = ttk.Label(bar, text="  CPU: --%", style="Status.TLabel")
        self._cpu_label.pack(side=tk.LEFT, padx=(20, 0))

        self._gpu_label = ttk.Label(bar, text="  GPU: --%", style="Status.TLabel")
        self._gpu_label.pack(side=tk.LEFT, padx=(20, 0))

        self._ram_label = ttk.Label(bar, text="  RAM: --%", style="Status.TLabel")
        self._ram_label.pack(side=tk.LEFT, padx=(20, 0))

        # Sizegrip
        ttk.Sizegrip(bar, style="TSizegrip").pack(side=tk.RIGHT)

    # ═══════════════════════════════════════════════════════
    # Config I/O
    # ═══════════════════════════════════════════════════════

    def _load_config_to_ui(self) -> None:
        """Load config from JSON and populate UI widgets."""
        self.config = AppConfig.from_json(self.config_path)

        # Populate path entries
        for key, var in self._path_entries.items():
            var.set(getattr(self.config, key, ""))

        # Populate other widgets
        for key, var in self._spin_vars.items():
            val = getattr(self.config, key, "")
            if isinstance(var, tk.BooleanVar):
                var.set(bool(val))
            else:
                var.set(str(val) if val is not None else "")

        self._log(f"Config loaded from {os.path.basename(self.config_path)}", "system")

    def _read_ui_to_config(self) -> None:
        """Read values from UI widgets back into the config object."""
        for key, var in self._path_entries.items():
            setattr(self.config, key, var.get())

        for key, var in self._spin_vars.items():
            field_type = type(getattr(self.config, key))
            raw = var.get()

            if field_type is bool:
                # BooleanVar.get() returns bool
                setattr(self.config, key, bool(var.get()))
            elif field_type is int:
                try:
                    setattr(self.config, key, int(raw))
                except ValueError:
                    setattr(self.config, key, 0)
            elif field_type is float:
                try:
                    setattr(self.config, key, float(raw))
                except ValueError:
                    setattr(self.config, key, 0.0)
            else:
                setattr(self.config, key, raw)

    def _save_config(self) -> None:
        """Save current UI values to JSON config file."""
        self._read_ui_to_config()
        self.config.to_json(self.config_path)
        self._log(f"Config saved to {os.path.basename(self.config_path)}", "system")

    # ═══════════════════════════════════════════════════════
    # Server Lifecycle (placeholder — Step 3)
    # ═══════════════════════════════════════════════════════

    def _start_server(self) -> None:
        """Start the llama.cpp server process."""
        self._read_ui_to_config()
        errors = self.config.validate()
        if errors:
            messagebox.showerror("Configuration Error",
                                 "Please fix the following errors:\n\n" + "\n".join(f"• {e}" for e in errors))
            return

        cmd = self.config.build_cmd_args()
        cmd_str = " ".join(f'"{a}"' if " " in a else a for a in cmd)
        self._log(f"CMD: {cmd_str}", "cmd")
        self._log("Starting server...", "system")

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError:
            self._log(f"ERROR: Executable not found: {cmd[0]}", "error")
            messagebox.showerror("Error", f"Cannot find server executable:\n{cmd[0]}")
            return
        except Exception as e:
            self._log(f"ERROR: Failed to start process: {e}", "error")
            messagebox.showerror("Error", f"Failed to start server:\n{e}")
            return

        # Start stdout reader thread
        thread = threading.Thread(target=self._read_stdout, daemon=True)
        thread.start()

        # Start log flush loop (only if not already running)
        if self._poll_id is None:
            self._flush_logs()

        # Update UI state
        self._set_server_running(True)

    def _stop_server(self) -> None:
        """Stop the llama.cpp server process."""
        if not self.process:
            return

        self._log("Stopping server...", "system")

        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._log("Server did not stop gracefully, force killing...", "warn")
                self.process.kill()
                self.process.wait(timeout=3)
        except Exception as e:
            self._log(f"Error stopping server: {e}", "error")

        self.process = None
        self._set_server_running(False)
        self._log("Server stopped", "system")

    def _set_server_running(self, running: bool) -> None:
        """Update UI elements to reflect server state."""
        if running:
            self._start_stop_btn.config(text="⏹  Stop Server", style="Danger.TButton",
                                        command=self._stop_server)
            self._status_label.config(text="●  Server: Running", style="StatusActive.TLabel")
            self._server_status_led.itemconfig(self._led_dot, fill=COLORS["green"])
            # Update tray tooltip
            if self.tray_icon:
                self.tray_icon.update_tooltip("Llama Server - Running")
        else:
            self._start_stop_btn.config(text="▶  Start Server", style="Primary.TButton",
                                        command=self._start_server)
            self._status_label.config(text="●  Server: Stopped", style="Status.TLabel")
            self._server_status_led.itemconfig(self._led_dot, fill=COLORS["red"])
            # Update tray tooltip
            if self.tray_icon:
                self.tray_icon.update_tooltip("Llama Server - Stopped")

    # ═══════════════════════════════════════════════════════
    # Log System
    # ═══════════════════════════════════════════════════════

    def _read_stdout(self) -> None:
        """Background thread: read lines from server stdout, push to queue."""
        if not self.process or not self.process.stdout:
            return

        ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

        try:
            for line in self.process.stdout:
                line = line.rstrip("\n")
                # Strip ANSI escape codes
                clean = ansi_re.sub("", line)
                if not clean.strip():
                    continue
                tag = self._classify_log(clean)
                self.log_queue.put((clean, tag))
        except Exception:
            pass
        finally:
            # Signal process exit
            self.log_queue.put(("── Server process exited ──", "system"))
            if self.process:
                self.after(0, self._on_server_exit)

    def _classify_log(self, line: str) -> str:
        """Classify a log line and return a tag name."""
        lower = line.lower()
        if "error" in lower or "exception" in lower or "fatal" in lower:
            return "error"
        if line.startswith("W") or "warn" in lower:
            return "warn"
        if "prx" in lower:
            return "proxy"
        if "srv" in lower:
            return "info"
        return "info"

    def _flush_logs(self) -> None:
        """Pull log entries from queue and display them. Called every 80ms."""
        count = 0
        while not self.log_queue.empty() and count < 100:
            try:
                text, tag = self.log_queue.get_nowait()
                self._log_text.insert(tk.END, text + "\n", tag)
                count += 1
            except queue.Empty:
                break

        if count:
            self._log_text.see(tk.END)

        self._poll_id = self.after(80, self._flush_logs)

    def _log(self, message: str, tag: str = "info") -> None:
        """Directly write a message to the log (for system messages)."""
        self._log_text.insert(tk.END, message + "\n", tag)
        self._log_text.see(tk.END)

    def _clear_log(self) -> None:
        """Clear all log output."""
        self._log_text.delete("1.0", tk.END)
        self._log("Log cleared", "system")

    def _on_server_exit(self) -> None:
        """Called when the server process exits unexpectedly."""
        if self.process:
            self.process = None
            self._set_server_running(False)

    # ═══════════════════════════════════════════════════════
    # Hardware Monitor
    # ═══════════════════════════════════════════════════════

    def _update_hardware_stats(self) -> None:
        """Update CPU, GPU, RAM status labels. Called every 2 seconds."""
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            self._cpu_label.config(text=f"  CPU: {cpu:.0f}%")
        except Exception:
            self._cpu_label.config(text="  CPU: N/A")

        try:
            ram = psutil.virtual_memory().percent
            self._ram_label.config(text=f"  RAM: {ram:.0f}%")
        except Exception:
            self._ram_label.config(text="  RAM: N/A")

        try:
            gpu = self._get_gpu_usage()
            self._gpu_label.config(text=f"  GPU: {gpu}")
        except Exception:
            self._gpu_label.config(text="  GPU: N/A")

        self._monitor_id = self.after(2000, self._update_hardware_stats)

    def _get_gpu_usage(self) -> str:
        """Query GPU utilization via nvidia-smi. Returns '--%' if unavailable."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0 and result.stdout.strip():
                return f"{result.stdout.strip()}%"
        except Exception:
            pass
        return "--%"

    # ═══════════════════════════════════════════════════════
    # System Tray
    # ═══════════════════════════════════════════════════════

    # _make_tray_image removed — using module-level _make_tray_icon_image()

    def _hide_to_tray(self) -> None:
        """Hide main window to system tray."""
        # Ensure tray icon exists (it's created via after(500), might not be ready yet)
        if not self.tray_icon:
            self._create_tray_icon()

        self.withdraw()

    def _create_tray_icon(self) -> None:
        """Create and show system tray icon. Called once at startup."""
        if self.tray_icon:
            return

        try:
            tooltip = "Llama Server - Stopped"

            self.tray_icon = WinTrayIcon(
                tooltip=tooltip,
                on_show=self._show_from_tray,
                on_exit=self._exit_app,
            )
            self.tray_icon.start()
        except Exception as e:
            self._log(f"Failed to create tray icon: {e}", "error")
            self.tray_icon = None

    def _poll_tray_actions(self) -> None:
        """Poll the tray action queue every 100ms. Runs on main thread."""
        try:
            while True:
                action = self._tray_action_queue.get_nowait()
                if action == "show":
                    self.deiconify()
                    self.lift()
                    # Use Win32 API to reliably bring window to foreground on Windows
                    self._win32_foreground_restore()
                elif action == "exit":
                    self._do_exit_app()
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll_tray_actions)

    def _win32_foreground_restore(self) -> None:
        """Restore window and bring to foreground using Win32 API.

        tkinter's focus_force() is unreliable on modern Windows (10/11)
        because SetForegroundWindow restrictions prevent background apps
        from stealing focus.  We use ShowWindow + SetForegroundWindow
        which works here because the user initiated the action via the
        tray icon that belongs to this process.
        """
        hwnd = self.winfo_id()
        if not hwnd:
            self.focus_force()
            return
        # SW_RESTORE = 9: activates and displays the window
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(hwnd)

    def _show_from_tray(self, _icon=None, _item=None) -> None:
        """Restore window from system tray. Called from tray callback."""
        self._tray_action_queue.put("show")

    def _exit_app(self, _icon=None, _item=None) -> None:
        """Full cleanup and exit. Called from tray callback."""
        self._tray_action_queue.put("exit")

    def _do_exit_app(self) -> None:
        """Main-thread implementation of exit cleanup."""
        if self._monitor_id:
            self.after_cancel(self._monitor_id)
            self._monitor_id = None
        self._stop_server()
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.destroy()

    def _on_close(self) -> None:
        """Handle window close button. Hide to tray if server is running."""
        if self.process:
            self._hide_to_tray()
        else:
            self._exit_app()


# ── Entry Point ────────────────────────────────────────────

def main() -> None:
    """Launch the Llama Launcher application."""
    app = LlamaLauncher()
    app.mainloop()


if __name__ == "__main__":
    main()
