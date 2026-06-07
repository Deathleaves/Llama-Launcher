## 🦙 Llama Launcher（驼羊启动器）

一个 Windows 桌面启动器，用于管理 [llama.cpp](https://github.com/ggerganov/llama.cpp) 推理服务器。提供 **浏览器 Web UI**、可视化配置、实时彩色日志、系统托盘常驻、硬件监控——告别复杂的命令行参数。

> **v2.0 更新**：UI 已从 tkinter 迁移到 Web 技术栈（FastAPI + HTML/CSS/JS），在浏览器中访问 `http://localhost:8083`，界面更流畅更美观。旧版 tkinter GUI 保留为 `llama_gui_tkinter.py`。

### ✨ 功能特性

- **🌐 浏览器 Web UI** — 现代暗色主题界面，CSS Grid 布局，可拖拽分割面板，文件浏览器 Modal。支持 Ctrl+S 快捷键保存配置。
- **可视化配置** — 所有 llama.cpp 服务器参数都有清晰界面。文件路径支持 Browse 按钮浏览本地目录。
- **一键启停** — 点击按钮启动或停止服务器。启动前自动校验配置。
- **实时彩色日志** — 通过 WebSocket 实时推送服务器输出，颜色标记：紫色=系统，红色=错误，橙色=警告，蓝色=代理，绿色=信息。
- **系统托盘常驻** — 右键菜单控制：Start/Stop Server、Open Web UI、Exit。左键打开浏览器。
- **硬件监控** — 状态栏每 2 秒更新 CPU、GPU（nvidia-smi）和 RAM。
- **配置持久化** — JSON 文件保存，启动自动加载。
- **静默启动** — 双击 `llama_webui.bat`，最小化控制台 + 托盘图标控制。

### 📋 运行要求

- Windows 10/11（64 位）
- Python 3.10+
- [llama.cpp](https://github.com/ggerganov/llama.cpp) 的 `llama-server.exe`
- GGUF 格式的模型文件

### 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 克隆本项目
git clone https://github.com/Deathleaves/Llama-Launcher.git
cd Llama-Launcher

# 3. 启动 Web UI
python server.py

# 或者双击（静默启动）：
llama_webui.bat
```

浏览器自动打开 `http://localhost:8083`。

### 🎮 使用说明

1. **配置路径** — 用 Browse 按钮设置 `llama-server.exe`、模型文件、视觉 MMProj 路径。
2. **调整参数** — 线程数、批处理大小、GPU 层数、上下文长度、端口、温度等。
3. **保存配置** — 点击 `Save Config` 或按 `Ctrl+S`。
4. **启动服务器** — 点击 `Start Server`，右侧日志面板实时显示输出。
5. **托盘控制** — 右键托盘图标：Start Server / Stop Server / Open Web UI / Exit。

### 🏗️ 项目结构

```
Llama-Launcher/
├── server.py              # FastAPI 后端（API + WebSocket + 进程管理 + 硬件监控）
├── config.py              # 配置数据类（校验、JSON 读写、命令行构建）
├── tray_win32.py          # Win32 系统托盘（ctypes，零外部依赖）
├── static/
│   └── index.html         # 自包含 Web 前端（暗色主题 SPA）
├── llama_webui.bat        # 双击启动（pythonw 静默）
├── llama_gui.bat          # 启动脚本（同 llama_webui.bat）
├── llama_gui_tkinter.py   # 旧版 tkinter GUI（回退方案）
├── requirements.txt       # Python 依赖
└── requirements.md        # 完整需求文档
```

### ⚙️ 配置项参考

| 分类 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| **文件路径** | Server Path | — | `llama-server.exe` 路径 |
| | Model Path | — | `.gguf` 模型文件路径 |
| | Vision MMProj | — | 多模态视觉投影文件（可选） |
| **性能参数** | Threads | 32 | CPU 线程数 |
| | Batch Size | 2048 | 批处理大小 |
| | GPU Layers | 150 | GPU 卸载层数 |
| | Context Length | 131072 | 上下文窗口长度 |
| **服务器** | Port | 8081 | 推理服务端口 |
| | Temperature | 0.8 | 采样温度 |
| | Model Alias | — | 模型别名 |
| | Chat Template | chatml | 对话模板格式 |
| | Log Level | INFO | 日志级别 |
| | Flash Attention | 开启 | 启用 Flash Attention |
| | Lock Memory (mlock) | 开启 | 锁定内存防止交换 |

### 🔧 技术栈

- **后端**：FastAPI + uvicorn（异步 WebSocket 推送）
- **前端**：纯 HTML/CSS/JS（单文件 SPA，无构建步骤，离线可用）
- **托盘**：原生 Win32 API via `ctypes`（零外部依赖）
- **硬件监控**：`psutil` + NVIDIA `nvidia-smi`
- **配置**：`dataclasses` + JSON
- **主题**：Catppuccin Mocha 暗色

### 🔧 CLI 参数

```
python server.py [--host HOST] [--port PORT] [--no-tray] [--no-browser]

  --host HOST      绑定地址（默认 127.0.0.1）
  --port PORT      Web UI 端口（默认 8083）
  --no-tray        禁用系统托盘
  --no-browser     不自动打开浏览器
```
