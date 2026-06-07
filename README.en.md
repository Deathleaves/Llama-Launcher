## 🦙 Llama Launcher

A Windows desktop launcher for [llama.cpp](https://github.com/ggerganov/llama.cpp) inference server. Provides a **browser-based Web UI**, visual configuration, real-time color-coded logs, system tray integration, and hardware monitoring — no more memorizing complex command-line arguments.

> **v2.0 Update**: UI migrated from tkinter to web stack (FastAPI + HTML/CSS/JS). Access via browser at `http://localhost:8083` for a smoother, more polished experience. The old tkinter GUI is kept as `llama_gui_tkinter.py` for fallback.

### ✨ Features

- **🌐 Browser Web UI** — Modern dark-themed interface with CSS Grid layout, draggable split panels, file browser modal. Ctrl+S shortcut for saving config.
- **Visual Configuration** — All llama.cpp server parameters in a clean interface. Browse buttons for local file navigation.
- **One-Click Start/Stop** — Launch or stop the server with a single button. Config validated before launching.
- **Real-Time Color-Coded Logs** — WebSocket-powered live log streaming with color tags: purple=system, red=error, orange=warn, blue=proxy, green=info.
- **System Tray Integration** — Right-click menu: Start/Stop Server, Open Web UI, Exit. Left-click opens browser.
- **Hardware Monitoring** — Status bar updates CPU, GPU (nvidia-smi), and RAM every 2 seconds.
- **Persistent Config** — JSON file auto-saves and auto-loads.
- **Silent Launch** — Double-click `llama_webui.bat` for minimized console + tray icon control.

### 📋 Requirements

- Windows 10/11 (64-bit)
- Python 3.10+
- [llama.cpp](https://github.com/ggerganov/llama.cpp) `llama-server.exe`
- A GGUF format model file

### 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Clone the project
git clone https://github.com/Deathleaves/Llama-Launcher.git
cd Llama-Launcher

# 3. Launch Web UI
python server.py

# Or double-click (silent launch):
llama_webui.bat
```

Browser opens automatically at `http://localhost:8083`.

### 🎮 Usage

1. **Configure paths** — Set `llama-server.exe`, model file, and optional vision MMProj paths using Browse.
2. **Adjust parameters** — Threads, batch size, GPU layers, context length, port, temperature, and more.
3. **Save config** — Click `Save Config` or press `Ctrl+S`.
4. **Start server** — Click `Start Server`. Watch real-time output in the log panel.
5. **Tray control** — Right-click tray icon: Start Server / Stop Server / Open Web UI / Exit.

### 🏗️ Project Structure

```
Llama-Launcher/
├── server.py              # FastAPI backend (API + WebSocket + process mgmt + hardware)
├── config.py              # Configuration dataclass (validation, JSON I/O, CLI builder)
├── tray_win32.py          # Win32 system tray (ctypes, zero external deps)
├── static/
│   └── index.html         # Self-contained Web frontend (dark theme SPA)
├── llama_webui.bat        # Double-click launcher (silent)
├── llama_gui.bat          # Launcher script (same as llama_webui.bat)
├── llama_gui_tkinter.py   # Legacy tkinter GUI (fallback)
├── requirements.txt       # Python dependencies
└── requirements.md        # Full requirements document
```

### ⚙️ Configuration Reference

| Section | Parameter | Default | Description |
|---------|-----------|---------|-------------|
| **File Paths** | Server Path | — | Path to `llama-server.exe` |
| | Model Path | — | Path to `.gguf` model file |
| | Vision MMProj | — | Multi-modal projection file (optional) |
| **Performance** | Threads | 32 | CPU thread count |
| | Batch Size | 2048 | Batch processing size |
| | GPU Layers | 150 | Layers offloaded to GPU |
| | Context Length | 131072 | Context window size |
| **Server** | Port | 8081 | Inference server port |
| | Temperature | 0.8 | Sampling temperature |
| | Model Alias | — | Display name for the model |
| | Chat Template | chatml | Conversation template format |
| | Log Level | INFO | Logging verbosity |
| | Flash Attention | On | Enable flash attention |
| | Lock Memory (mlock) | On | Prevent memory swapping |

### 🔧 Tech Stack

- **Backend**: FastAPI + uvicorn (async WebSocket push)
- **Frontend**: Vanilla HTML/CSS/JS (single-file SPA, zero build step, fully offline)
- **Tray**: Native Win32 API via `ctypes` (zero external dependency)
- **Hardware Monitor**: `psutil` + NVIDIA `nvidia-smi`
- **Config**: `dataclasses` + JSON
- **Theme**: Catppuccin Mocha dark

### 🔧 CLI Options

```
python server.py [--host HOST] [--port PORT] [--no-tray] [--no-browser]

  --host HOST      Bind address (default 127.0.0.1)
  --port PORT      Web UI port (default 8083)
  --no-tray        Disable system tray icon
  --no-browser     Do not auto-open browser
```
