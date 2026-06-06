"""
config.py — AppConfig dataclass for Llama Launcher.

Pure data layer with no tkinter dependency. Handles JSON I/O,
validation, and command-line argument construction.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class AppConfig:
    """Configuration for the llama.cpp server launcher."""

    # File paths
    server_path: str = ""
    model_path: str = ""
    mmproj_path: str = ""

    # Performance parameters
    threads: int = 32
    batch_size: int = 2048
    gpu_layers: int = 150
    context_length: int = 131072

    # Server parameters
    port: int = 8081
    temperature: float = 0.8
    model_alias: str = ""
    chat_template: str = "chatml"
    log_level: str = "INFO"
    flash_attn: bool = True
    mlock: bool = True

    # Chat template options
    CHAT_TEMPLATES: tuple[str, ...] = field(
        default=("chatml", "llama3", "llama2", "vicuna", "alpaca", "command-r",
                 "deepseek", "gemma", "mistral", "phi", "zephyr"),
        init=False,
        repr=False,
    )

    # Log level options
    LOG_LEVELS: tuple[str, ...] = field(
        default=("DEBUG", "INFO", "WARN", "ERROR"),
        init=False,
        repr=False,
    )

    # ── JSON I/O ──────────────────────────────────────────

    @classmethod
    def from_json(cls, path: str) -> "AppConfig":
        """Load config from a JSON file. Returns default config if file doesn't exist."""
        if not os.path.exists(path):
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = json.load(f)

        # Map JSON keys to dataclass fields (only copy known fields)
        field_names = {f.name for f in fields(cls)}
        values: dict[str, Any] = {}
        for key, val in raw.items():
            if key in field_names:
                values[key] = val

        return cls(**values)

    def to_json(self, path: str) -> None:
        """Save config to a JSON file."""
        data: dict[str, Any] = {}
        for f in fields(self):
            if f.init:
                data[f.name] = getattr(self, f.name)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── Validation ─────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return a list of error messages. Empty list means valid."""
        errors: list[str] = []

        # Server executable
        if not self.server_path:
            errors.append("Server path is required.")
        elif not os.path.exists(self.server_path):
            errors.append(f"Server executable not found: {self.server_path}")

        # Model file
        if not self.model_path:
            errors.append("Model path is required.")
        elif not os.path.exists(self.model_path):
            errors.append(f"Model file not found: {self.model_path}")
        elif not self.model_path.lower().endswith(".gguf"):
            errors.append(f"Model file should be a .gguf file: {self.model_path}")

        # MMProj (optional; validate only if provided)
        if self.mmproj_path and not os.path.exists(self.mmproj_path):
            errors.append(f"MMProj file not found: {self.mmproj_path}")

        # Port range
        if not (1024 <= self.port <= 65535):
            errors.append(f"Port must be between 1024 and 65535, got {self.port}.")

        # Threads
        if self.threads < 1:
            errors.append(f"Threads must be at least 1, got {self.threads}.")

        # Batch size
        if self.batch_size < 1:
            errors.append(f"Batch size must be at least 1, got {self.batch_size}.")

        # GPU layers
        if self.gpu_layers < 0:
            errors.append(f"GPU layers cannot be negative, got {self.gpu_layers}.")

        # Context length
        if self.context_length < 256:
            errors.append(f"Context length must be at least 256, got {self.context_length}.")

        # Temperature
        if not (0.0 <= self.temperature <= 2.0):
            errors.append(f"Temperature must be between 0.0 and 2.0, got {self.temperature}.")

        # Log level
        if self.log_level not in self.LOG_LEVELS:
            errors.append(f"Log level must be one of {self.LOG_LEVELS}, got '{self.log_level}'.")

        # Chat template
        if not self.chat_template:
            errors.append("Chat template cannot be empty.")

        return errors

    # ── Command line builder ──────────────────────────────

    def build_cmd_args(self) -> list[str]:
        """Build the command line argument list for llama-server.exe."""
        args = [self.server_path]

        # Model
        args.extend(["-m", self.model_path])

        # Optional MMProj (for vision models)
        if self.mmproj_path:
            args.extend(["--mmproj", self.mmproj_path])

        # Performance
        args.extend(["-t", str(self.threads)])
        args.extend(["-b", str(self.batch_size)])
        args.extend(["-ngl", str(self.gpu_layers)])
        args.extend(["-c", str(self.context_length)])

        # Server
        args.extend(["--port", str(self.port)])
        args.extend(["--host", "0.0.0.0"])
        args.extend(["--temp", str(self.temperature)])

        if self.model_alias:
            args.extend(["--alias", self.model_alias])

        if self.chat_template:
            args.extend(["--chat-template", self.chat_template])

        # Memory lock (prevent swapping)
        if self.mlock:
            args.append("--mlock")

        # Flash attention (explicit value to avoid consuming next arg)
        if self.flash_attn:
            args.extend(["--flash-attn", "1"])

        return args


# ── Standalone test ────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Force UTF-8 for Windows console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    test_path = os.path.join(os.path.dirname(__file__), "llama_config.json")

    print("=== Loading config ===")
    cfg = AppConfig.from_json(test_path)
    for f in fields(cfg):
        if f.init:
            print(f"  {f.name}: {getattr(cfg, f.name)!r}")

    print("\n=== Validation ===")
    errs = cfg.validate()
    if errs:
        print("Errors:")
        for e in errs:
            print(f"  [ERR] {e}")
    else:
        print("  [OK] No validation errors")

    print("\n=== Command line ===")
    cmd = cfg.build_cmd_args()
    print("  " + " ".join(f'"{a}"' if " " in a else a for a in cmd))

    print("\n=== Round-trip test ===")
    roundtrip_path = os.path.join(os.path.dirname(__file__), "_test_roundtrip.json")
    cfg.to_json(roundtrip_path)
    cfg2 = AppConfig.from_json(roundtrip_path)
    match = cfg == cfg2
    print(f"  Round-trip: {'[OK] pass' if match else '[FAIL]'}")
    if not match:
        print(f"  Original: {cfg}")
        print(f"  Reloaded: {cfg2}")
    os.remove(roundtrip_path)
    sys.exit(0 if match else 1)
