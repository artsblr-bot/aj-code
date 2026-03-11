"""Model router with 4-tier system for AJax Code."""
import json
import logging
from pathlib import Path

import psutil
import requests
from rich.console import Console

console = Console()
log = logging.getLogger("ajaxcode.models")

OLLAMA_BASE = "http://localhost:11434"

TIERS = {
    1: {"model": "qwen2.5-coder:1.5b",  "label": "⚡ Tier 1", "min_ram": 0},
    2: {"model": "deepseek-coder:6.7b",  "label": "🔥 Tier 2", "min_ram": 6},
    3: {"model": "qwen2.5-coder:14b",    "label": "🧠 Tier 3", "min_ram": 16},
    4: {"model": "qwen2.5-coder:32b",    "label": "💪 Tier 4", "min_ram": 32},
}

TASK_COMPLEXITY = {
    "simple":   1,
    "medium":   2,
    "complex":  3,
    "hardest":  4,
}

SIMPLE_KEYWORDS = [
    "open", "read", "show", "print", "explain line", "what is", "what does",
    "git status", "git log", "list files", "ls", "pwd", "cd",
]
MEDIUM_KEYWORDS = [
    "write function", "fix bug", "fix error", "refactor", "add feature",
    "add method", "update", "change", "modify", "rename",
]
COMPLEX_KEYWORDS = [
    "build module", "architect", "write tests", "full review", "review all",
    "optimize", "redesign", "create class", "implement", "add support for",
]
HARDEST_KEYWORDS = [
    "build entire", "build app", "create app", "complex algorithm",
    "system design", "full stack", "from scratch", "build me a",
]


class ModelRouter:
    def __init__(self):
        self._available_models: list[str] = []
        self._refresh_available()

    def _refresh_available(self) -> None:
        try:
            r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
            if r.status_code == 200:
                data = r.json()
                self._available_models = [m["name"] for m in data.get("models", [])]
        except Exception:
            self._available_models = []

    def available_ram_gb(self) -> float:
        try:
            mem = psutil.virtual_memory()
            return mem.available / (1024 ** 3)
        except Exception:
            return 4.0

    def total_ram_gb(self) -> float:
        try:
            return psutil.virtual_memory().total / (1024 ** 3)
        except Exception:
            return 8.0

    def ram_warning(self) -> bool:
        try:
            return psutil.virtual_memory().percent > 85
        except Exception:
            return False

    def classify_task(self, message: str) -> str:
        msg = message.lower()
        for kw in HARDEST_KEYWORDS:
            if kw in msg:
                return "hardest"
        for kw in COMPLEX_KEYWORDS:
            if kw in msg:
                return "complex"
        for kw in MEDIUM_KEYWORDS:
            if kw in msg:
                return "medium"
        for kw in SIMPLE_KEYWORDS:
            if kw in msg:
                return "simple"
        # default heuristic by message length
        if len(message) < 60:
            return "simple"
        elif len(message) < 200:
            return "medium"
        return "complex"

    def _model_installed(self, model_name: str) -> bool:
        self._refresh_available()
        # check exact or prefix match
        for m in self._available_models:
            if m == model_name or m.startswith(model_name.split(":")[0]):
                return True
        return False

    def select_model(self, task: str = "medium", override: str | None = None) -> tuple[str, str]:
        """Returns (model_name, tier_label)."""
        if override and override != "auto":
            return override, "🔧 Custom"

        ram = self.total_ram_gb()
        complexity = TASK_COMPLEXITY.get(task, 2)

        # pick tier based on both RAM and task complexity
        if ram < 6:
            desired_tier = 1
        elif ram < 16:
            desired_tier = min(2, complexity)
        elif ram < 32:
            desired_tier = min(3, complexity)
        else:
            desired_tier = min(4, complexity)

        # try from desired tier down to tier 1 for availability
        for tier_num in range(desired_tier, 0, -1):
            model = TIERS[tier_num]["model"]
            label = TIERS[tier_num]["label"]
            if self._model_installed(model):
                return model, label

        # fallback: return tier 1 even if not installed (will fail gracefully)
        return TIERS[1]["model"], TIERS[1]["label"]

    def unload_model(self, model_name: str) -> None:
        """Release model from RAM after complex task."""
        try:
            requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=10,
            )
        except Exception:
            pass

    def list_installed(self) -> list[str]:
        self._refresh_available()
        return self._available_models

    def pull_model(self, model_name: str) -> None:
        """Pull a model via Ollama API (streaming)."""
        try:
            console.print(f"[cyan]Pulling {model_name}... this may take a while.[/cyan]")
            r = requests.post(
                f"{OLLAMA_BASE}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=600,
            )
            for line in r.iter_lines():
                if line:
                    data = json.loads(line)
                    status = data.get("status", "")
                    if "total" in data and "completed" in data:
                        pct = int(data["completed"] / data["total"] * 100)
                        console.print(f"\r  {status} {pct}%", end="")
            console.print(f"\n[green]✅ {model_name} ready.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to pull {model_name}: {e}[/red]")
