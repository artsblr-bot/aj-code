"""AJax Code — entry point."""
import logging
import sys
import traceback
from pathlib import Path

from rich.console import Console

console = Console()


def _setup_logging() -> None:
    log_dir = Path.home() / ".ajaxcode" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "ajaxcode.log"),
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


def main() -> None:
    _setup_logging()

    try:
        from .config import get_config
        from .agent import AgentLoop
        from .models import ModelRouter
        from .ui import REPL, print_startup

        cfg = get_config()
        user_name = cfg.get("user_name", "Aarav")

        router = ModelRouter()
        model, _ = router.select_model("simple", cfg.get("preferred_model", "auto"))
        ram = router.total_ram_gb()

        # Check Ollama
        import requests
        try:
            requests.get("http://localhost:11434/api/tags", timeout=3)
        except Exception:
            console.print("[red]ERROR: Ollama is not running![/red]")
            console.print("[yellow]Start it with: ollama serve[/yellow]")
            sys.exit(1)

        agent = AgentLoop()
        project = agent.ctx.project_summary or "No project detected"

        print_startup(user_name, model, ram, project)

        repl = REPL(agent)
        repl.run()

    except KeyboardInterrupt:
        console.print("\n[cyan]Session ended. Goodbye![/cyan]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        console.print("[dim]Check ~/.ajaxcode/logs/ajaxcode.log for details[/dim]")
        logging.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
