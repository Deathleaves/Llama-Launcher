@echo off
cd /d "%~dp0"
start /min python.exe "%~dp0server.py" --port 8083
