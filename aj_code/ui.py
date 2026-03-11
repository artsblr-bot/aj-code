"""Rich terminal UI for AJax Code."""
import sys
from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

try:
    import pyfiglet
    HAS_FIGLET = True
except ImportError:
    HAS_FIGLET = False

console = Console()

HISTORY_FILE = Path.home() / ".ajaxcode" / "history.txt"
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

SLASH_COMMANDS = {
    "/help":    "Show all commands",
    "/model":   "Show or change current model",
    "/context": "Show context usage %",
    "/project": "Show project summary",
    "/history": "Show conversation history",
    "/clear":   "Clear conversation",
    "/undo":    "Undo last file change",
    "/diff":    "Show changes made this session",
    "/commit":  "Commit all changes with AI message",
    "/exit":    "Exit AJax Code",
}


def print_startup(user_name: str, model: str, ram_gb: float, project: str) -> None:
    if HAS_FIGLET:
        banner = pyfiglet.figlet_format("AJax Code", font="slant")
        console.print(f"[bold white]{banner}[/bold white]")
    else:
        console.print("[bold white]===  AJax Code  ===[/bold white]\n")

    console.print(f"  [dim]v1.0.0  ·  Author: Aarav J  ·  License: MIT[/dim]")
    console.print(f"  [cyan]Model:[/cyan] {model}")
    console.print(f"  [cyan]RAM:[/cyan] {ram_gb:.1f} GB available")
    if project and project != "No project detected":
        console.print(f"  [cyan]Project:[/cyan] {project[:80]}")
    console.print()
    console.print(f"[bold green]Hey {user_name}! What are we building today?[/bold green]")
    console.print("[dim]Type /help for commands  ·  Ctrl+C to exit[/dim]\n")


def print_help() -> None:
    console.print("\n[bold cyan]AJax Code Commands[/bold cyan]")
    for cmd, desc in SLASH_COMMANDS.items():
        console.print(f"  [green]{cmd:<12}[/green] {desc}")
    console.print()


def print_action(msg: str) -> None:
    console.print(f"  [dim]{msg}[/dim]")


def print_error(msg: str) -> None:
    console.print(f"[red]ERROR: {msg}[/red]")


def print_success(msg: str) -> None:
    console.print(f"[green]OK: {msg}[/green]")


def print_warning(msg: str) -> None:
    console.print(f"[yellow]WARNING: {msg}[/yellow]")


def stream_response(agent, user_message: str, confirm_cb: Callable) -> str:
    """Stream Ajax's response token by token."""
    buf = []
    console.print()
    console.print("[bold cyan]Ajax[/bold cyan]", end=" ")

    def on_token(token: str) -> None:
        buf.append(token)
        console.print(token, end="", highlight=False)

    def on_action(msg: str) -> None:
        console.print()
        print_action(msg)
        console.print("[bold cyan]Ajax[/bold cyan]", end=" ")

    full = agent.chat(
        user_message,
        print_token=on_token,
        print_action=on_action,
        confirm_destructive=confirm_cb,
    )
    console.print("\n")
    return full


def confirm_destructive(prompt: str) -> bool:
    console.print(f"\n[yellow]WARNING: {prompt}[/yellow]")
    answer = console.input("[yellow]Proceed? (yes/no): [/yellow]").strip().lower()
    return answer in ("yes", "y")


class REPL:
    def __init__(self, agent) -> None:
        self.agent = agent
        self.session = PromptSession(
            history=FileHistory(str(HISTORY_FILE)),
        )

    def handle_slash(self, cmd: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        parts = cmd.strip().split(None, 1)
        c = parts[0].lower()

        if c == "/help":
            print_help()
        elif c == "/exit":
            console.print("\n[cyan]Goodbye! Keep building great things.[/cyan]")
            sys.exit(0)
        elif c == "/clear":
            self.agent.ctx.messages.clear()
            console.print("[green]Conversation cleared.[/green]")
        elif c == "/context":
            pct = self.agent.ctx.context_pct()
            console.print(f"[cyan]Context usage: {pct}%[/cyan]")
        elif c == "/project":
            summary = self.agent.ctx.project_summary or "No project detected."
            console.print(f"[cyan]Project:[/cyan] {summary}")
        elif c == "/history":
            msgs = self.agent.ctx.get_messages()
            for m in msgs[-10:]:
                role = m["role"]
                color = "green" if role == "user" else "cyan"
                console.print(f"[{color}]{role}:[/{color}] {m['content'][:100]}")
        elif c == "/undo":
            result = self.agent.undo_last()
            console.print(f"[cyan]{result}[/cyan]")
        elif c == "/model":
            installed = self.agent.router.list_installed()
            console.print(f"[cyan]Installed models:[/cyan] {', '.join(installed) or 'none'}")
            current_model = self.agent.cfg.get("preferred_model", "auto")
            console.print(f"[cyan]Preferred:[/cyan] {current_model}")
        elif c == "/diff":
            changes = self.agent.ctx.recent_changes
            if changes:
                for ch in changes:
                    console.print(f"  [dim]{ch}[/dim]")
            else:
                console.print("[dim]No changes recorded this session.[/dim]")
        elif c == "/commit":
            stream_response(
                self.agent,
                "Please git add all changed files and commit them with a descriptive message.",
                confirm_destructive,
            )
        else:
            console.print(f"[red]Unknown command: {c}[/red]  Type /help for list.")
        return True

    def run(self) -> None:
        while True:
            try:
                user_input = self.session.prompt("> ").strip()
                if not user_input:
                    continue
                if user_input.startswith("/"):
                    self.handle_slash(user_input)
                    continue
                stream_response(self.agent, user_input, confirm_destructive)
            except KeyboardInterrupt:
                console.print("\n[dim](Ctrl+C again to quit, or type /exit)[/dim]")
            except EOFError:
                console.print("\n[cyan]Goodbye![/cyan]")
                break
