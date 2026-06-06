<div align="right">

[📖 English](README.md)

</div>

## 🦙 Llama Launcher（驼羊启动器）

一个 Windows 桌面 GUI 启动器，用于管理 [llama.cpp](https://github.com/ggerganov/llama.cpp) 推理服务器。提供可视化配置、实时彩色日志、系统托盘常驻、硬件监控——告别复杂的命令行参数。

### ✨ 功能特性

- **可视化配置** — 所有 llama.cpp 服务器参数都有清晰的暗色主题界面。服务器程序、模型文件、视觉投影文件支持 Browse 按钮选择。每个设置都有数字调节器和下拉框。
- **一键启停** — 点击按钮启动或停止服务器。启动前自动校验配置，避免因路径错误导致的启动失败。
- **实时彩色日志** — 服务器输出实时流式显示，语法颜色标记：紫色=系统事件，红色=错误，橙色=警告，蓝色=代理消息，绿色=信息。
- **系统托盘常驻** — 最小化到 Windows 通知区域。左键单击恢复窗口，右键弹出菜单。运行时任务栏无任何占用。
- **硬件监控** — 状态栏实时显示 CPU、GPU（NVIDIA 通过 nvidia-smi）和内存使用率。
- **配置持久化** — 所有设置保存为 JSON 文件，下次启动自动加载。
- **零控制台窗口** — 通过 `pythonw.exe` 启动。无终端窗口、无子进程控制台——只有 GUI 和托盘图标。

### 📋 运行要求

- Windows 10/11（64 位）
- Python 3.10+
- [llama.cpp](https://github.com/ggerganov/llama.cpp) 的 `llama-server.exe`
- GGUF 格式的模型文件

### 🚀 快速开始

```bash
# 1. 安装依赖
pip install psutil Pillow

# 2. 克隆或下载本项目
git clone https://github.com/Deathleaves/Llama-Launcher.git
cd Llama-Launcher

# 3. 运行（无控制台窗口）
pythonw llama_gui.py

# 或者双击：
llama_gui.bat
```

### 🎮 使用说明

1. **配置文件路径** — 用 Browse 按钮设置 `llama-server.exe`、模型 `.gguf` 文件以及可选的视觉 MMProj 文件路径。
2. **调整参数** — 设置线程数、批处理大小、GPU 层数、上下文长度、端口、温度等参数。
3. **启动服务器** — 点击 `Start Server`，在日志面板查看实时输出。
4. **隐藏到托盘** — 关闭窗口或点击 `Hide to Tray`，服务器继续运行。
5. **恢复窗口** — 左键点击托盘图标，或右键 → `Show Window`。

### 🏗️ 项目结构

```
Llama-Launcher/
├── llama_gui.py        # 主程序（GUI + 进程管理 + 日志 + 托盘 + 监控）
├── config.py           # 配置数据类（校验、JSON 读写、命令行构建）
├── llama_gui.bat       # Windows 启动脚本（pythonw、UTF-8）
└── requirements.md     # 完整需求文档
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
| **服务器** | Port | 8081 | HTTP 服务端口 |
| | Temperature | 0.8 | 采样温度 |
| | Model Alias | — | 模型别名 |
| | Chat Template | chatml | 对话模板格式 |
| | Log Level | INFO | 日志级别 |
| | Flash Attention | 开启 | 启用 Flash Attention |
| | Lock Memory | 开启 | 锁定内存防止交换 (mlock) |

### 🔧 技术栈

- **GUI**：Python `tkinter`（标准库，无需额外安装）
- **托盘**：通过 `ctypes` 调用原生 Win32 API（无外部依赖）
- **硬件监控**：`psutil` + NVIDIA `nvidia-smi`
- **配置**：`dataclasses` + JSON

### 📄 许可证

MIT License
