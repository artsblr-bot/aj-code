"""AJax Code configuration and first-run setup."""
import json
import platform
import subprocess
import sys
from pathlib import Path

import psutil
from rich.console import Console
from rich.prompt import Prompt

console = Console()

CONFIG_DIR = Path.home() / ".ajaxcode"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOGS_DIR = CONFIG_DIR / "logs"
MEMORY_DB = CONFIG_DIR / "memory.db"

DEFAULT_CONFIG = {
    "user_name": "Aarav",
    "preferred_model": "auto",
    "theme": "default",
    "web_search": True,
    "auto_execute": True,
    "max_retries": 5,
    "context_limit": 32000,
}


def detect_os() -> str:
    system = platform.system()
    if system == "Linux":
        return "linux"
    elif system == "Darwin":
        return "mac"
    elif system == "Windows":
        return "windows"
    return "unknown"


def detect_ram_gb() -> float:
    try:
        mem = psutil.virtual_memory()
        return mem.total / (1024 ** 3)
    except Exception:
        return 8.0


def detect_ollama_running() -> bool:
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def detect_git_installed() -> bool:
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def get_best_model_for_ram(ram_gb: float) -> str:
    if ram_gb < 6:
        return "qwen2.5-coder:1.5b"
    elif ram_gb < 16:
        return "deepseek-coder:6.7b"
    elif ram_gb < 32:
        return "qwen2.5-coder:14b"
    else:
        return "qwen2.5-coder:32b"


def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            # merge with defaults for any missing keys
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        console.print(f"[red]Warning: Could not save config: {e}[/red]")


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def first_run_wizard() -> dict:
    """Run once on first launch to set user preferences."""
    console.print("\n[cyan]Welcome to AJax Code! Let's get you set up.[/cyan]\n")

    name = Prompt.ask("What's your name?", default="Aarav")

    ram = detect_ram_gb()
    best_model = get_best_model_for_ram(ram)
    console.print(f"[green]Detected {ram:.1f} GB RAM. Recommended model: {best_model}[/green]")

    cfg = dict(DEFAULT_CONFIG)
    cfg["user_name"] = name
    cfg["preferred_model"] = "auto"
    cfg["_first_run_done"] = True

    save_config(cfg)
    console.print(f"\n[green]All set, {name}! Let's build something great.[/green]\n")
    return cfg


def get_config() -> dict:
    ensure_dirs()
    cfg = load_config()
    if not cfg.get("_first_run_done"):
        cfg = first_run_wizard()
    return cfg
