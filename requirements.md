# Llama.cpp Server Launcher 需求文档

---

## 1. 产品概述

一个 Windows 桌面 GUI 启动器，用于管理和运行 llama.cpp 推理服务器。支持多模态视觉模型（Qwen-VL），提供可视化配置、实时日志查看、系统托盘常驻等功能。

### 1.1 目标

需要在 Windows 环境下便捷启动和管理本地大语言模型推理服务的开发者。

### 1.2 核心功能

- 避免记忆和手写复杂的 llama.cpp 命令行参数
- 配置可视化，所见即所得
- 服务状态一目了然，日志带颜色标记
- 后台常驻系统托盘，不占用任务栏空间
- GPU 、CPU、内存使用监控

---

## 2. 功能需求

### 2.1 配置管理

#### 2.1.1 文件路径配置

| 字段 | 说明 | 输入方式 |
|------|------|----------|
| Server Path | llama-server.exe 的路径 | 文本输入 + Browse 按钮 |
| Model Path | GGUF 模型文件路径 | 文本输入 + Browse 按钮 |
| Vision MMProj | 多模态视觉投影文件路径 | 文本输入 + Browse 按钮 |

- 路径不存在时启动前校验并提示错误

#### 2.1.2 性能参数配置

| 字段 | 说明 | 默认值 |
|------|------|--------|
| Threads | CPU 线程数 | 32 |
| Batch Size | 批处理大小 | 2048 |
| GPU Layers | GPU 卸载层数 | 150 |
| Context Length | 上下文窗口长度 | 131072 |

#### 2.1.3 服务器参数配置

| 字段 | 说明 | 默认值 |
|------|------|--------|
| Port | 服务端口 | 8081 |
| Temperature | 采样温度 | 0.8 |
| Model Alias | 模型别名 | — |
| Chat Template | 对话模板格式 | chatml |
| Log Level | 日志级别 | INFO（可选 DEBUG/WARN/ERROR） |
| Flash Attention | 是否启用 Flash Attention | 开启 |

#### 2.1.4 配置持久化

- 所有配置保存为 JSON 文件（可参考项目文件夹中的`llama_config.json`）
- 启动时自动加载上次保存的配置
- "Save Config" 按钮手动保存

---

### 2.3 实时日志系统

#### 2.3.1 日志采集

- 通过独立线程异步读取子进程 stdout
- 自动过滤 ANSI 转义码
- 根据消息内容自动标注标签（SRV=Server, PRX=Proxy）

#### 2.3.2 日志显示

- 使用 ScrolledText 控件，暗色主题（黑底彩字）
- 颜色标记规则：

| 级别 | 颜色 | 触发条件 |
|------|------|----------|
| System | 紫色 | 生命周期事件（启动/停止/CMD） |
| Error | 红色 | 含 "error" 或 "exception" |
| Warn | 橙色 | 含 "W" 或 "WARN" |
| Proxy | 蓝色 | 代理进程输出 |
| Info | 绿色 | 其他 |

- 每 80ms 从队列批量刷新，避免 UI 卡顿
- "Clear Log" 按钮清空日志区域

---

### 2.4 系统托盘

#### 2.4.1 托盘图标

- 启动程序后自动初始化托盘消息接收窗口
- 点击 "Hide to Tray" 或关闭窗口时，若服务正在运行：
  - 在 Windows 通知区域显示托盘图标
  - 主窗口隐藏（不关闭）
  - 悬浮提示显示 "Llama Server - Running"
- 停止服务后悬浮提示更新为 "Llama Server - Stopped"
- 托盘退出后，自动卸载模型，释放内存

#### 2.4.2 左键交互

- 单击 / 双击托盘图标 → 恢复显示主窗口

#### 2.4.3 右键菜单

- 右键托盘图标弹出菜单：
  - **显示窗口**：恢复主窗口并移除托盘图标
  - **退出**：停止所有服务并关闭程序

---

### 2.5 UI 布局

参考发的图片

- Config 标签页内容超出时支持鼠标滚轮滚动
- 底部 Sizegrip 支持拖拽缩放

---

## 4. 文件结构

```
D:/AI/llama启动器/
├── llama_gui.py            # 主程序
├── llama_gui.bat           # 启动脚本（解决中文路径编码问题）
├── llama_config.json       # 用户配置文件（自动生成）
├── content-fix-proxy.py    # Content-Fix 代理脚本
└── tray_debug.log          # 托盘调试日志（运行时生成）
```
