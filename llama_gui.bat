@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
start "" pythonw.exe "%~dp0llama_gui.py"
