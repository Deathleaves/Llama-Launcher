## 🦙 Llama Launcher

A Windows desktop GUI launcher for [llama.cpp](https://github.com/ggerganov/llama.cpp) inference server. Provides visual configuration, real-time color-coded log viewing, system tray integration, and hardware monitoring — no more memorizing complex command-line arguments.

### ✨ Features

- **Visual Configuration** — All llama.cpp server parameters in a clean dark-themed UI. File pickers for server executable, model, and vision projection files. Numeric spinners and dropdowns for every setting.
- **One-Click Start/Stop** — Launch or stop the server with a single button. Validation catches misconfiguration before launching.
- **Real-Time Color-Coded Logs** — Server output streamed live with syntax-colored tags: purple for system events, red for errors, orange for warnings, blue for proxy messages, green for info.
- **System Tray Integration** — Minimize to Windows notification area. Left-click to restore, right-click for menu. Zero taskbar clutter while running.
- **Hardware Monitoring** — Live CPU, GPU (NVIDIA via nvidia-smi), and RAM usage displayed in the status bar.
- **Persistent Config** — All settings saved as JSON, auto-loaded on next launch.
- **Zero Console Windows** — Launched via `pythonw.exe`. No terminal window, no child console — only the GUI and tray icon.

### 📋 Requirements

- Windows 10/11 (64-bit)
- Python 3.10+
- [llama.cpp](https://github.com/ggerganov/llama.cpp) `llama-server.exe`
- A GGUF format model file

### 🚀 Quick Start

```bash
# 1. Install dependencies
pip install psutil Pillow

# 2. Clone or download this project
git clone https://github.com/Deathleaves/Llama-Launcher.git
cd Llama-Launcher

# 3. Run (no console window)
pythonw llama_gui.py

# Or double-click:
llama_gui.bat
```

### 🎮 Usage

1. **Configure paths** — Set your `llama-server.exe`, model `.gguf`, and optional vision MMProj file paths using Browse buttons.
2. **Adjust parameters** — Tune threads, batch size, GPU layers, context length, port, temperature, and more.
3. **Start the server** — Click `Start Server`. Watch the log panel for real-time output.
4. **Hide to tray** — Close the window or click `Hide to Tray`. The server keeps running.
5. **Restore** — Left-click the tray icon or right-click → `Show Window`.

### 🏗️ Project Structure

```
Llama-Launcher/
├── llama_gui.py        # Main application (GUI + process + log + tray + monitor)
├── config.py           # Configuration dataclass (validation, JSON I/O, CLI builder)
├── llama_gui.bat       # Windows launcher script (pythonw, UTF-8)
└── requirements.md     # Full requirements document (Chinese)
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
| **Server** | Port | 8081 | HTTP server port |
| | Temperature | 0.8 | Sampling temperature |
| | Model Alias | — | Display name for the model |
| | Chat Template | chatml | Conversation template format |
| | Log Level | INFO | Logging verbosity |
| | Flash Attention | On | Enable flash attention |
| | Lock Memory | On | Prevent memory swapping (mlock) |

### 🔧 Tech Stack

- **GUI**: Python `tkinter` (stdlib, no extra install)
- **Tray**: Native Win32 API via `ctypes` (no external dependency)
- **Hardware Monitor**: `psutil` + NVIDIA `nvidia-smi`
- **Config**: `dataclasses` + JSON
