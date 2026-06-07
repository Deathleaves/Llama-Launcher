"""
server.py — Llama Server Launcher (Web UI Backend)

FastAPI application that serves the web UI and manages the llama.cpp
inference server lifecycle. Replaces the tkinter GUI with a browser-based
interface while preserving all functionality.

Usage:
    python server.py [--host 127.0.0.1] [--port 8083] [--no-tray] [--no-browser]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import AppConfig

# ── Constants ────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CONFIG_PATH = BASE_DIR / "llama_config.json"
APP_TITLE = "Llama Server Launcher"

# Catppuccin Mocha log tag colors (for frontend reference)
LOG_TAGS: dict[str, str] = {
    "system": "lavender",
    "error": "red",
    "warn": "peach",
    "proxy": "blue",
    "info": "green",
    "cmd": "teal",
}

logger = logging.getLogger("llama-launcher")


# ── Pydantic Models ──────────────────────────────────────────

class ConfigUpdate(BaseModel):
    """Partial config update — all fields optional."""
    server_path: str | None = None
    model_path: str | None = None
    mmproj_path: str | None = None
    threads: int | None = None
    batch_size: int | None = None
    gpu_layers: int | None = None
    context_length: int | None = None
    port: int | None = None
    temperature: float | None = None
    model_alias: str | None = None
    chat_template: str | None = None
    log_level: str | None = None
    flash_attn: bool | None = None
    mlock: bool | None = None


class FileBrowseResult(BaseModel):
    path: str
    parent: str | None
    entries: list[dict[str, Any]]


class StatusResponse(BaseModel):
    running: bool
    pid: int | None = None


# ── Connection Manager (WebSocket broadcast) ────────────────

class ConnectionManager:
    """Manages active WebSocket connections for broadcasting."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, message: dict):
        """Send JSON to all connected clients."""
        stale = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._connections.remove(ws)

    async def broadcast_log(self, text: str, tag: str):
        await self.broadcast({
            "type": "log",
            "text": text,
            "tag": tag,
            "ts": time.time(),
        })

    async def broadcast_hardware(self, cpu: float, gpu: str, ram: float):
        await self.broadcast({
            "type": "hardware",
            "cpu": round(cpu, 1),
            "gpu": gpu,
            "ram": round(ram, 1),
        })

    async def broadcast_server_status(self, running: bool, pid: int | None = None):
        await self.broadcast({
            "type": "server_status",
            "running": running,
            "pid": pid,
        })

    @property
    def connected(self) -> bool:
        return len(self._connections) > 0


# ── Process Manager ──────────────────────────────────────────

class ProcessManager:
    """Manages the llama-server.exe subprocess lifecycle."""

    def __init__(self, log_queue: asyncio.Queue, conn_mgr: ConnectionManager):
        self.process: subprocess.Popen | None = None
        self._log_queue = log_queue
        self._conn_mgr = conn_mgr
        self._reader_thread: threading.Thread | None = None
        self._ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def get_pid(self) -> int | None:
        return self.process.pid if self.process else None

    async def start(self, cmd: list[str]) -> None:
        """Launch llama-server.exe."""
        if self.is_running():
            raise RuntimeError("Server is already running")

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
            raise RuntimeError(f"Executable not found: {cmd[0]}")
        except Exception as e:
            raise RuntimeError(f"Failed to start process: {e}")

        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()

        await self._log_queue.put(("Server started", "system"))
        await self._conn_mgr.broadcast_server_status(True, self.process.pid)

    async def stop(self) -> None:
        """Gracefully stop the server."""
        if not self.process:
            return

        await self._log_queue.put(("Stopping server...", "system"))

        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                await self._log_queue.put(
                    ("Server did not stop gracefully, force killing...", "warn"))
                self.process.kill()
                self.process.wait(timeout=3)
        except Exception as e:
            await self._log_queue.put((f"Error stopping server: {e}", "error"))

        self.process = None
        await self._log_queue.put(("Server stopped", "system"))
        await self._conn_mgr.broadcast_server_status(False)

    def _read_stdout(self) -> None:
        """Background thread: read lines from server stdout."""
        if not self.process or not self.process.stdout:
            return

        try:
            for line in self.process.stdout:
                line = line.rstrip("\n")
                clean = self._ansi_re.sub("", line)
                if not clean.strip():
                    continue
                tag = self._classify_log(clean)
                # Thread-safe enqueue
                try:
                    self._log_queue.put_nowait((clean, tag))
                except asyncio.QueueFull:
                    pass
        except Exception:
            pass
        finally:
            try:
                self._log_queue.put_nowait(
                    ("── Server process exited ──", "system"))
            except asyncio.QueueFull:
                pass
            # Signal main loop that process exited
            self.process = None

    def _classify_log(self, line: str) -> str:
        """Classify a log line (same logic as original llama_gui.py)."""
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


# ── Hardware Monitor ─────────────────────────────────────────

class HardwareMonitor:
    """Polls hardware stats every 2s and broadcasts via WebSocket."""

    def __init__(self, conn_mgr: ConnectionManager):
        self._conn_mgr = conn_mgr
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self):
        while True:
            try:
                cpu = psutil.cpu_percent(interval=0.1)
                ram = psutil.virtual_memory().percent
                gpu = await self._get_gpu_usage()
                await self._conn_mgr.broadcast_hardware(cpu, gpu, ram)
            except Exception:
                pass
            await asyncio.sleep(2)

    async def _get_gpu_usage(self) -> str:
        """Query GPU utilization via nvidia-smi."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return f"{stdout.decode().strip()}%"
        except Exception:
            pass
        return "--%"

    def get_snapshot(self) -> dict:
        """Synchronous hardware snapshot for REST API."""
        try:
            cpu = psutil.cpu_percent(interval=0.1)
        except Exception:
            cpu = 0.0
        try:
            ram = psutil.virtual_memory().percent
        except Exception:
            ram = 0.0
        # GPU not available synchronously (would block)
        return {"cpu": cpu, "gpu": "--%", "ram": ram}


# ── FastAPI Application ─────────────────────────────────────

app = FastAPI(title=APP_TITLE, version="2.0.0", docs_url=None, redoc_url=None)

# Global state (initialized in main())
config: AppConfig = AppConfig()
proc_mgr: ProcessManager | None = None
hw_monitor: HardwareMonitor | None = None
conn_mgr: ConnectionManager = ConnectionManager()
log_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
shutdown_event: asyncio.Event = asyncio.Event()


# ── Static Files ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the single-page application."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>UI not found</h1><p>static/index.html is missing.</p>",
            status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


# ── Config API ──────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Return current config as JSON."""
    data = {}
    from dataclasses import fields
    for f in fields(config):
        if f.init:
            data[f.name] = getattr(config, f.name)
    return data


@app.put("/api/config")
async def update_config(body: ConfigUpdate):
    """Partial config update — validate and save."""
    updates = body.model_dump(exclude_none=True)
    for key, val in updates.items():
        if hasattr(config, key):
            setattr(config, key, val)

    errors = config.validate()
    if errors:
        return JSONResponse(
            {"ok": False, "errors": errors}, status_code=400)

    config.to_json(str(CONFIG_PATH))
    await conn_mgr.broadcast_log(
        f"Config saved to {CONFIG_PATH.name}", "system")
    return {"ok": True}


@app.post("/api/config/validate")
async def validate_config():
    """Validate current config without saving."""
    errors = config.validate()
    return {"valid": len(errors) == 0, "errors": errors}


# ── File Browse API ──────────────────────────────────────────

@app.get("/api/files/browse")
async def browse_files(path: str = ""):
    """Browse the filesystem for file selection."""
    if not path:
        # Return list of drives on Windows
        import string
        drives = []
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append({
                    "name": f"{letter}: Drive",
                    "type": "dir",
                    "path": drive_path,
                    "size": None,
                })
        return FileBrowseResult(path="", parent=None, entries=drives)

    if not os.path.exists(path):
        return JSONResponse({"error": "Path not found"}, status_code=404)

    # Security: only allow directory browsing
    if os.path.isfile(path):
        parent_dir = os.path.dirname(path)
        return FileBrowseResult(
            path=path, parent=parent_dir, entries=[])

    entries = []
    try:
        for entry in sorted(os.listdir(path)):
            full = os.path.join(path, entry)
            is_dir = os.path.isdir(full)
            try:
                size = os.path.getsize(full) if not is_dir else None
            except OSError:
                size = None
            entries.append({
                "name": entry,
                "type": "dir" if is_dir else "file",
                "path": full,
                "size": size,
            })
    except PermissionError:
        return JSONResponse({"error": "Permission denied"}, status_code=403)

    parent = os.path.dirname(path) if path else None
    return FileBrowseResult(path=path, parent=parent, entries=entries)


# ── Server Lifecycle API ─────────────────────────────────────

@app.post("/api/server/start")
async def start_server():
    """Start the llama.cpp server."""
    global proc_mgr
    assert proc_mgr is not None

    errors = config.validate()
    if errors:
        return JSONResponse(
            {"ok": False, "error": "\n".join(errors)}, status_code=400)

    if proc_mgr.is_running():
        return {"ok": False, "error": "Server is already running"}

    cmd = config.build_cmd_args()
    cmd_str = " ".join(f'"{a}"' if " " in a else a for a in cmd)
    await conn_mgr.broadcast_log(f"CMD: {cmd_str}", "cmd")

    try:
        await proc_mgr.start(cmd)
        return {"ok": True, "pid": proc_mgr.get_pid()}
    except RuntimeError as e:
        await conn_mgr.broadcast_log(f"ERROR: {e}", "error")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/server/stop")
async def stop_server():
    """Stop the llama.cpp server."""
    global proc_mgr
    assert proc_mgr is not None
    await proc_mgr.stop()
    return {"ok": True}


@app.get("/api/server/status", response_model=StatusResponse)
async def server_status():
    """Get current server status."""
    global proc_mgr
    assert proc_mgr is not None
    return StatusResponse(
        running=proc_mgr.is_running(),
        pid=proc_mgr.get_pid(),
    )


# ── Hardware API ─────────────────────────────────────────────

@app.get("/api/hardware")
async def hardware_snapshot():
    """Get current hardware stats snapshot."""
    global hw_monitor
    assert hw_monitor is not None
    return hw_monitor.get_snapshot()


# ── Shutdown API ─────────────────────────────────────────────

@app.post("/api/shutdown")
async def shutdown():
    """Gracefully stop server and exit."""
    global proc_mgr, shutdown_event
    assert proc_mgr is not None
    if proc_mgr.is_running():
        await proc_mgr.stop()
    shutdown_event.set()
    return {"ok": True}


# ── WebSocket ────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket for real-time log, hardware, and status updates."""
    await conn_mgr.connect(ws)

    # Send current server status on connect
    if proc_mgr:
        await ws.send_json({
            "type": "server_status",
            "running": proc_mgr.is_running(),
            "pid": proc_mgr.get_pid(),
        })

    try:
        while True:
            # Keep connection alive, listen for client messages
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30)
                # Client messages are optional (e.g., ping)
                if data == "ping":
                    await ws.send_text("pong")
            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await ws.send_json({"type": "heartbeat"})
                except Exception:
                    break
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        conn_mgr.disconnect(ws)


# ── Background Tasks ─────────────────────────────────────────

async def log_broadcast_loop():
    """Continuously read from log_queue and broadcast to WebSocket clients."""
    while not shutdown_event.is_set():
        try:
            text, tag = await asyncio.wait_for(log_queue.get(), timeout=0.5)
            await conn_mgr.broadcast_log(text, tag)
        except asyncio.TimeoutError:
            continue
        except Exception:
            pass


async def process_monitor_loop():
    """Monitor process exit from stdout reader thread."""
    global proc_mgr
    assert proc_mgr is not None
    while not shutdown_event.is_set():
        if proc_mgr.process and proc_mgr.process.poll() is not None:
            # Process exited
            proc_mgr.process = None
            try:
                log_queue.put_nowait(("── Server process exited ──", "system"))
            except asyncio.QueueFull:
                pass
            await conn_mgr.broadcast_server_status(False)
        await asyncio.sleep(1)


# ── Main Entry Point ────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description=f"{APP_TITLE} Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8083, help="Port for web UI")
    parser.add_argument("--no-tray", action="store_true", help="Disable system tray icon")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")
    return parser.parse_args()


async def main_async(args):
    global config, proc_mgr, hw_monitor

    # Load config
    config = AppConfig.from_json(str(CONFIG_PATH))

    # Initialize managers
    proc_mgr = ProcessManager(log_queue, conn_mgr)
    hw_monitor = HardwareMonitor(conn_mgr)

    # Log startup
    await conn_mgr.broadcast_log(
        f"Llama Launcher Web UI starting on http://{args.host}:{args.port}", "system")
    await conn_mgr.broadcast_log(
        f"Config loaded from {CONFIG_PATH.name}", "system")

    # Start hardware monitor
    await hw_monitor.start()

    # Start background tasks
    asyncio.create_task(log_broadcast_loop())
    asyncio.create_task(process_monitor_loop())

    # Open browser
    if not args.no_browser:
        url = f"http://{args.host}:{args.port}"
        webbrowser.open(url)

    # Import and start tray (if on Windows and not disabled)
    tray = None
    if sys.platform == "win32" and not args.no_tray:
        try:
            from tray_win32 import WinTrayIcon
            loop = asyncio.get_running_loop()

            def on_show():
                webbrowser.open(url)

            def on_start_server():
                asyncio.run_coroutine_threadsafe(_tray_start_server(), loop)

            def on_stop_server():
                asyncio.run_coroutine_threadsafe(_tray_stop_server(), loop)

            def on_exit():
                asyncio.run_coroutine_threadsafe(_tray_exit(), loop)

            async def _tray_start_server():
                if not proc_mgr.is_running():
                    errors = config.validate()
                    if errors:
                        return
                    cmd = config.build_cmd_args()
                    try:
                        await proc_mgr.start(cmd)
                        if tray:
                            tray.set_server_running(True)
                            tray.update_tooltip("Llama Server - Running")
                    except RuntimeError:
                        pass

            async def _tray_stop_server():
                if proc_mgr.is_running():
                    await proc_mgr.stop()
                    if tray:
                        tray.set_server_running(False)
                        tray.update_tooltip("Llama Server - Stopped")

            async def _tray_exit():
                if proc_mgr.is_running():
                    await proc_mgr.stop()
                if tray:
                    tray.stop()
                shutdown_event.set()

            tray = WinTrayIcon(
                tooltip="Llama Server - Stopped",
                on_show=on_show,
                on_exit=on_exit,
                on_start=on_start_server,
                on_stop=on_stop_server,
            )
            tray.start()
            logger.info("System tray icon started")
        except Exception as e:
            logger.warning(f"Failed to create tray icon: {e}")

    # Wait for shutdown signal
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass

    # Cleanup
    logger.info("Shutting down...")
    if hw_monitor:
        await hw_monitor.stop()
    if proc_mgr and proc_mgr.is_running():
        await proc_mgr.stop()
    if tray:
        tray.stop()
    logger.info("Goodbye.")


def main():
    args = parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Import uvicorn here to avoid import-time side effects
    import uvicorn

    # Configure uvicorn
    uvicorn_config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(uvicorn_config)

    async def run_all():
        # Run uvicorn and main_async concurrently
        server_task = asyncio.create_task(server.serve())
        bg_task = asyncio.create_task(main_async(args))

        # If uvicorn exits immediately (e.g. port in use), abort startup
        done, _ = await asyncio.wait(
            [server_task, bg_task],
            timeout=1.0,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if server_task in done:
            # Server crashed — check if port is occupied by another instance
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            port_busy = s.connect_ex((args.host, args.port)) == 0
            s.close()
            if port_busy:
                logger.info(
                    f"Port {args.port} is already in use — "
                    f"another instance may already be running. "
                    f"Opening browser to http://{args.host}:{args.port}"
                )
                if not args.no_browser:
                    webbrowser.open(f"http://{args.host}:{args.port}")
                return
            else:
                exc = server_task.exception()
                logger.error(f"Server failed to start: {exc}")
                return

        # Wait for shutdown signal to propagate
        await shutdown_event.wait()

        # Shutdown uvicorn
        server.should_exit = True
        await server_task

        # Cancel background task
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except OSError as e:
        if "10048" in str(e) or "address" in str(e).lower():
            logger.error(
                f"Port {args.port} is already in use. "
                f"Try a different port: python server.py --port {args.port + 1}"
            )
        else:
            logger.error(f"OS error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
