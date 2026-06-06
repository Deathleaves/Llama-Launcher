# Llama Launcher — Design Spec

**Date**: 2026-06-05  
**Status**: Approved  
**Author**: User + Claude  

## 1. Overview

A Windows desktop GUI launcher for llama.cpp inference server. Provides visual configuration, real-time log viewing with color coding, system tray integration, and hardware monitoring.

**Target user**: Developers who need to conveniently start and manage local LLM inference services on Windows.

## 2. Architecture

### 2.1 File Structure

```
D:\SynologyDrive\AI-Projects\Llama-Launcher\
├── llama_gui.py              # Main entry point + UI + process + log + tray
├── llama_gui.bat             # Windows launcher script (pythonw.exe, chcp 65001)
├── llama_config.json         # User configuration (auto-generated on first run)
├── config.py                 # Configuration dataclass + JSON I/O + validation
└── docs\
    └── superpowers\
        └── specs\
            └── 2026-06-05-llama-launcher-design.md
```

### 2.2 Class Design

#### `config.py` — Pure data layer (no tkinter dependency)

```
@dataclass
class AppConfig:
    # File paths
    server_path: str = ""
    model_path: str = ""
    mmproj_path: str = ""

    # Performance
    threads: int = 32
    batch_size: int = 2048
    gpu_layers: int = 150
    context_length: int = 131072

    # Server
    port: int = 8081
    temperature: float = 0.8
    model_alias: str = ""
    chat_template: str = "chatml"
    log_level: str = "INFO"
    flash_attn: bool = True

    @classmethod
    def from_json(cls, path: str) -> "AppConfig"
    
    def to_json(self, path: str) -> None
    
    def validate(self) -> list[str]
        # Returns list of error messages. Empty = valid.
        # Checks: server_path exists, model_path exists and is .gguf,
        #         mmproj_path exists if non-empty, port in range,
        #         threads > 0, context_length > 0, etc.
    
    def build_cmd_args(self) -> list[str]
        # Returns command line argument list for llama-server.exe
        # Example: ["D:/.../llama-server.exe", "-m", "model.gguf",
        #           "--port", "8081", "-t", "32", ...]
```

#### `llama_gui.py` — Main application

```
class LlamaLauncher(tk.Tk):
    """Main application window. Single class containing all logic."""
    
    # --- Core state ---
    config: AppConfig
    process: subprocess.Popen | None
    log_queue: queue.Queue
    tray_icon: pystray.Icon | None
    _poll_id: str  # after() ID for log polling

    # --- Lifecycle ---
    def __init__(self) -> None
    def run(self) -> None          # mainloop() wrapper

    # --- UI construction ---
    def _setup_theme(self) -> None       # Dark theme colors, ttk styles
    def _build_toolbar(self, parent) -> None
    def _build_config_panel(self, parent) -> None  # Scrolled canvas
    def _build_log_panel(self, parent) -> None
    def _build_status_bar(self, parent) -> None
    def _create_path_row(self, parent, label, config_attr) -> ttk.Frame
    def _create_spinbox_row(self, parent, label, config_attr, range) -> ttk.Frame
    def _create_combo_row(self, parent, label, config_attr, values) -> ttk.Frame

    # --- Config I/O ---
    def _load_config_to_ui(self) -> None
    def _read_ui_to_config(self) -> None
    def _save_config(self) -> None

    # --- Server lifecycle ---
    def _start_server(self) -> None
    def _stop_server(self) -> None
    def _on_server_exit(self) -> None

    # --- Logging ---
    def _read_stdout(self) -> None      # Runs in background thread
    def _classify_log(self, line: str) -> str  # Returns tag name
    def _flush_logs(self) -> None       # Called every 80ms via after()

    # --- System tray ---
    def _create_tray_icon(self) -> pystray.Icon
    def _hide_to_tray(self) -> None
    def _show_from_tray(self) -> None
    def _exit_app(self) -> None         # Full cleanup

    # --- Hardware monitor ---
    def _update_hardware_stats(self) -> None  # Called every 2000ms

    # --- Window protocol ---
    def _on_close(self) -> None         # Minimize to tray instead of exit
```

### 2.3 UI Component Tree

```
LlamaLauncher (tk.Tk, title="Llama Server Launcher", dark theme)
│
├── ttk.Frame: toolbar
│   ├── ttk.Label: "Llama Server Launcher"
│   └── ttk.Button: "Hide to Tray"  → _hide_to_tray()
│
├── ttk.PanedWindow (horizontal, sash)
│   │
│   ├── [Left] ttk.Frame: config_panel
│   │   ├── Canvas (yscrollcommand linked)
│   │   │   └── ttk.Frame (scrollable, bind <MouseWheel>)
│   │   │       ├── ttk.Labelframe: "File Paths"
│   │   │       │   ├── path_row: Server Path    [Entry..........] [Browse]
│   │   │       │   ├── path_row: Model Path     [Entry..........] [Browse]
│   │   │       │   └── path_row: MMProj Path    [Entry..........] [Browse]
│   │   │       │
│   │   │       ├── ttk.Labelframe: "Performance"
│   │   │       │   ├── spinbox_row: Threads       [Spinbox: 1-256]
│   │   │       │   ├── spinbox_row: Batch Size    [Spinbox: 1-32768]
│   │   │       │   ├── spinbox_row: GPU Layers    [Spinbox: 0-999]
│   │   │       │   └── spinbox_row: Context Len   [Spinbox: 256-1048576]
│   │   │       │
│   │   │       ├── ttk.Labelframe: "Server"
│   │   │       │   ├── spinbox_row: Port          [Spinbox: 1024-65535]
│   │   │       │   ├── entry_row:   Temperature   [Entry: float]
│   │   │       │   ├── entry_row:   Model Alias    [Entry: text]
│   │   │       │   ├── combo_row:   Chat Template  [Combobox: chatml/llama3/...]
│   │   │       │   ├── combo_row:   Log Level      [Combobox: DEBUG/INFO/WARN/ERROR]
│   │   │       │   └── check_row:   Flash Attn     [Checkbutton]
│   │   │       │
│   │   │       └── button_area
│   │   │           ├── ttk.Button: "💾 Save Config"
│   │   │           ├── ttk.Button: "▶ Start Server" / "⏹ Stop Server"
│   │   │           └── ttk.Button: "🗑 Clear Log"
│   │   │
│   │   └── ttk.Scrollbar (linked to Canvas)
│   │
│   └── [Right] ttk.Frame: log_panel
│       ├── ttk.Frame: log_toolbar
│       │   ├── ttk.Label: "Server Log"
│       │   └── ttk.Button: "Clear Log"
│       └── tk.Text (ScrolledText, bg=#1e1e2e, fg=#cdd6f4)
│           # Tags: system(#cba6f7), error(#f38ba8), warn(#fab387),
│           #        proxy(#89b4fa), info(#a6e3a1)
│
└── ttk.Frame: status_bar
    ├── ttk.Label: "● Server: Stopped"
    ├── ttk.Label: "CPU: 0%"
    ├── ttk.Label: "GPU: 0%"
    ├── ttk.Label: "RAM: 0%"
    └── ttk.Sizegrip
```

### 2.4 Color Theme (Catppuccin Mocha)

| Role | Hex | Usage |
|------|------|-------|
| Base | #1e1e2e | Window background |
| Surface | #313244 | Frame/Labelframe background |
| Text | #cdd6f4 | Primary text |
| Subtext | #a6adc8 | Secondary text |
| Lavender | #cba6f7 | System log |
| Red | #f38ba8 | Error log |
| Peach | #fab387 | Warning log |
| Blue | #89b4fa | Proxy log |
| Green | #a6e3a1 | Info log / success |

## 3. Data Flow

### 3.1 Config Flow

```
llama_config.json ──[from_json()]──▶ AppConfig ──[_load_config_to_ui()]──▶ UI widgets
       ▲                                                                      │
       │                              [to_json()]                             │
       └──────────────────────────────────────────────────────────────────────┘
                                  _save_config()
```

### 3.2 Server Lifecycle

```
[Start] ──▶ _read_ui_to_config()
         ──▶ config.validate()
              ├── errors → messagebox.showerror(), return
              └── valid ──▶ config.build_cmd_args()
                        ──▶ Popen(cmd, stdout=PIPE, stderr=STDOUT,
                                  creationflags=CREATE_NO_WINDOW)
                        ──▶ Thread(_read_stdout).start()
                        ──▶ after(80, _flush_logs)
                        ──▶ Update UI state

[Stop]  ──▶ process.terminate()
        ──▶ process.wait(timeout=5)
             ├── timeout ──▶ process.kill()
             └── exited ──▶ log "Server stopped"
        ──▶ Update UI state

[Process exit] (detected in _read_stdout thread)
        ──▶ log_queue.put(("Server process exited", "system"))
        ──▶ root.after(0, _on_server_exit)
```

### 3.3 Log Pipeline

```
stdout line
  │
  ▼
_read_stdout() [background thread]
  ├── strip ANSI: re.sub(r'\x1b\[[0-9;]*m', '', line)
  ├── classify: "srv" in line → "info"
  │             "error" in line.lower() → "error"
  │             line.startswith("W") or "warn" in line → "warn"
  │             "prx" in line → "proxy"
  │             else → "info"
  └── log_queue.put((clean_line, tag))
        │
        ▼
_flush_logs() [main thread, every 80ms]
  ├── while not log_queue.empty():
  │     text, tag = log_queue.get_nowait()
  │     text_widget.insert(END, text + "\n", tag)
  └── text_widget.see(END)   # auto-scroll
  └── self._poll_id = self.after(80, self._flush_logs)
```

### 3.4 System Tray Flow

```
[Hide to Tray] or [X] button (WM_DELETE_WINDOW)
  │
  ├── if server running:
  │     self.withdraw()                    # Hide main window
  │     self.tray_icon.run_detached()      # Show tray icon
  │     # No taskbar entry
  │
  └── if server NOT running:
        _exit_app()                        # Full exit

[Left-click tray icon] → _show_from_tray()
  ├── self.tray_icon.stop()
  ├── self.deiconify()                     # Restore window
  └── self.lift()

[Right-click tray: Show Window] → _show_from_tray()
[Right-click tray: Exit] → _exit_app()
  ├── _stop_server()
  ├── self.tray_icon.stop()
  └── self.destroy()
```

## 4. Key Technical Decisions

### 4.1 Subprocess Management
- **CREATE_NO_WINDOW**: Prevents console window from appearing for llama-server.exe
- **Single process**: Only one server instance at a time; Start button disabled while running
- **Graceful shutdown**: terminate() first, kill() after 5s timeout

### 4.2 Log System
- **Queue-based**: Background thread pushes to `queue.Queue`, main thread pulls via `after()`
- **80ms batch interval**: Balances responsiveness with UI performance
- **ANSI stripping**: Regex removes escape sequences before display

### 4.3 System Tray
- **pystray**: Cross-platform tray library; uses win32api on Windows
- **Detached mode**: `run_detached()` so tray runs in its own thread without blocking
- **No taskbar**: `withdraw()` hides the tkinter window completely

### 4.4 Hardware Monitoring
- **psutil**: CPU percent, virtual memory
- **GPU**: Attempt nvidia-smi subprocess; fall back to "N/A" if unavailable
- **2-second interval**: Non-blocking via `after(2000, ...)`

### 4.5 No-Window Guarantee
- `.bat` uses `pythonw.exe` (no console)
- `Popen` with `CREATE_NO_WINDOW` (no child console)
- `withdraw()` hides the tkinter window from taskbar
- Only tray icon remains visible

## 5. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| tkinter | (stdlib) | GUI framework |
| pystray | latest | System tray icon |
| Pillow | latest | Tray icon image (required by pystray) |
| psutil | latest | CPU/RAM monitoring |

All installable via: `pip install pystray Pillow psutil`

## 6. Error Handling

| Scenario | Handling |
|----------|----------|
| Config file not found | Create with defaults |
| Config JSON invalid | Show warning, use defaults |
| server_path not found | Validate before start, show messagebox error |
| model_path not found | Validate before start, show messagebox error |
| Port already in use | llama-server reports error → shown in log |
| Process crashes | Detected in stdout thread → log + UI update |
| GPU monitor fails | Show "N/A", don't block UI |
| Tray icon fails | Log to file, continue with window mode |

## 7. Self-Review

- **No placeholders**: All sections complete
- **No contradictions**: Tray behavior consistent across sections  
- **Scoped properly**: Single application, no feature creep (proxy removed)
- **No ambiguity**: All behaviors specified with concrete values and conditions
- **Matches requirements.md**: All 2.1-2.5 sections covered; proxy/proxy_port removed per user decision
