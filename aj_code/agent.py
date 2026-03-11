"""Core agentic loop for AJax Code."""
import json
import logging
import re
from pathlib import Path
from typing import Callable, Generator

import requests
from rich.console import Console

from .config import get_config
from .context import ContextManager
from .models import ModelRouter
from .tools import ToolKit

log = logging.getLogger("ajaxcode.agent")
console = Console()

OLLAMA_BASE = "http://localhost:11434"

SYSTEM_TEMPLATE = """You are Ajax, an expert AI coding agent built into AJax Code.
You help {user_name} build, fix, and improve code.

You have full access to their computer through tools.
You execute tasks autonomously without asking for permission.
You are confident, capable, and friendly like JARVIS.

Current project: {project_summary}
Current file: {current_file}
Recent changes: {recent_changes}

When given a task:
1. Think about what needs to be done
2. Make a plan if it's complex
3. Execute each step using your tools
4. Verify everything works
5. Report clearly what you did

You write clean, well-commented, production-quality code.
You always handle errors gracefully.
You suggest improvements proactively but don't impose them.
Address user as {user_name}.

TOOL CALLING FORMAT:
To use a tool, output it exactly like this (on its own line):
<tool>tool_name</tool><params>{{"key": "value"}}</params>

Available tools:
- read_file: params: path
- write_file: params: path, content
- edit_file: params: path, old, new
- delete_file: params: path
- list_files: params: path, pattern
- search_in_files: params: query, path
- create_directory: params: path
- git_status: params: (none)
- git_diff: params: (none)
- git_add: params: files (list or string)
- git_commit: params: message
- git_push: params: (none)
- git_pull: params: (none)
- git_log: params: n
- git_branch: params: name (optional), switch (bool)
- git_clone: params: url, path
- run_command: params: cmd, cwd (optional)
- install_package: params: name, manager (pip/npm/cargo)
- check_command_exists: params: cmd
- web_search: params: query
- fetch_url: params: url
- search_docs: params: query, framework
- download_file: params: url, path
- run_python: params: code (inline Python string) OR path (path to .py file) OR cmd (shell command string) — use exactly one
- run_javascript: params: code
- run_bash: params: code
- lint_code: params: path
- format_code: params: path
- find_syntax_errors: params: code, language
- scan_project: params: path
- get_project_summary: params: (none)
- find_function: params: name, path
- find_usages: params: name, path

When a task is complex, first output a numbered plan, then execute it step by step.
After each tool call, briefly report what you found/did before moving on.
"""

TOOL_PATTERN = re.compile(
    r"<tool>([\w]+)</tool>\s*<params>(.*?)</params>",
    re.DOTALL,
)

DESTRUCTIVE_TOOLS = {"delete_file", "git_push"}


class AgentLoop:
    def __init__(self) -> None:
        self.cfg = get_config()
        self.router = ModelRouter()
        self.toolkit = ToolKit()
        self.ctx = ContextManager(self.cfg.get("context_limit", 32000))
        self._undo_stack: list[dict] = []  # {path, original_content}
        self._init_project()

    def _init_project(self) -> None:
        result = self.toolkit.scan_project(".")
        if result["success"]:
            summary = self.toolkit.get_project_summary()
            self.ctx.set_project(
                summary["result"] if summary["success"] else "Unknown project",
                str(Path.cwd()),
            )

    def _build_system_prompt(self) -> str:
        return SYSTEM_TEMPLATE.format(
            user_name=self.cfg.get("user_name", "Aarav"),
            project_summary=self.ctx.project_summary or "No project detected",
            current_file=self.ctx.current_file or "None",
            recent_changes=", ".join(self.ctx.recent_changes[-5:]) or "None",
        )

    def _call_ollama_stream(
        self, model: str, messages: list[dict]
    ) -> Generator[str, None, None]:
        try:
            resp = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={"model": model, "messages": messages, "stream": True},
                stream=True,
                timeout=300,
            )
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            yield f"\n[Error communicating with Ollama: {e}]"

    def _parse_tool_calls(self, text: str) -> list[tuple[str, dict]]:
        calls = []
        for m in TOOL_PATTERN.finditer(text):
            tool_name = m.group(1).strip()
            params_raw = m.group(2).strip()
            try:
                params = json.loads(params_raw) if params_raw else {}
            except json.JSONDecodeError:
                params = {}
            calls.append((tool_name, params))
        return calls

    def _execute_tool(
        self, name: str, params: dict,
        print_action: Callable[[str], None] | None = None,
        confirm_destructive: Callable[[str], bool] | None = None,
    ) -> dict:
        if name in DESTRUCTIVE_TOOLS and confirm_destructive:
            if not confirm_destructive(f"Run {name} with {params}?"):
                return {"success": False, "result": "Cancelled by user", "error": None}

        # save undo info for file writes
        if name == "write_file":
            path = params.get("path", "")
            p = Path(path).expanduser()
            if p.exists():
                try:
                    self._undo_stack.append({
                        "path": str(p),
                        "original": p.read_text(encoding="utf-8", errors="replace"),
                    })
                except Exception:
                    pass

        method = getattr(self.toolkit, name, None)
        if method is None:
            return {"success": False, "result": None, "error": f"Unknown tool: {name}"}

        try:
            result = method(**params)
        except TypeError as e:
            result = {"success": False, "result": None, "error": str(e)}

        if result.get("success") and name in ("write_file", "edit_file"):
            self.ctx.note_change(f"{name}({params.get('path', '')})")

        return result

    def undo_last(self) -> str:
        if not self._undo_stack:
            return "Nothing to undo."
        entry = self._undo_stack.pop()
        try:
            Path(entry["path"]).write_text(entry["original"])
            return f"Restored {entry['path']}"
        except Exception as e:
            return f"Undo failed: {e}"

    def chat(
        self,
        user_message: str,
        print_token: Callable[[str], None] | None = None,
        print_action: Callable[[str], None] | None = None,
        confirm_destructive: Callable[[str], bool] | None = None,
    ) -> str:
        # search memory for relevant context
        relevant = self.ctx.search_memory(user_message)
        mem_context = "\n".join(relevant) if relevant else ""

        task = self.router.classify_task(user_message)
        model, tier_label = self.router.select_model(
            task, self.cfg.get("preferred_model", "auto")
        )

        if self.router.ram_warning():
            if print_action:
                print_action("WARNING: RAM usage > 85% — responses may be slow")

        if print_action:
            print_action(f"Using {tier_label} ({model})")

        # build messages
        system_content = self._build_system_prompt()
        if mem_context:
            system_content += f"\n\nRelevant past context:\n{mem_context}"

        self.ctx.add_message("user", user_message)
        messages = [{"role": "system", "content": system_content}] + self.ctx.get_messages()

        full_response = ""
        retries = 0
        max_retries = self.cfg.get("max_retries", 5)
        turn = 0
        max_turns = 10
        _last_error: str | None = None
        _repeated_error_count = 0

        while turn < max_turns:
            turn += 1
            chunk_buf = ""

            for token in self._call_ollama_stream(model, messages):
                chunk_buf += token
                full_response += token
                if print_token:
                    print_token(token)

            # parse tool calls from this turn's output
            tool_calls = self._parse_tool_calls(chunk_buf)
            if not tool_calls:
                break  # no more tools needed

            # execute tools and feed results back
            tool_results_text = ""
            for tool_name, tool_params in tool_calls:
                if print_action:
                    print_action(f"🔧 {tool_name}({', '.join(f'{k}={repr(v)[:40]}' for k,v in tool_params.items())})")

                result = self._execute_tool(
                    tool_name, tool_params,
                    print_action=print_action,
                    confirm_destructive=confirm_destructive,
                )

                ok = result.get("success")
                res_val = result.get("result", "")
                err_val = result.get("error", "")

                if ok:
                    display = str(res_val)[:1000] if res_val else "OK"
                    if print_action:
                        print_action(f"  OK {tool_name}: {display[:80]}")
                    tool_results_text += f"\nTool {tool_name} result:\n{display}\n"
                else:
                    if print_action:
                        print_action(f"  FAILED {tool_name}: {err_val}")
                    tool_results_text += f"\nTool {tool_name} error: {err_val}\n"

                    # self-healing: stop if same error repeats twice or max retries hit
                    retries += 1
                    if err_val == _last_error:
                        _repeated_error_count += 1
                    else:
                        _last_error = err_val
                        _repeated_error_count = 1

                    if _repeated_error_count >= 2 or retries >= max_retries:
                        tool_results_text += (
                            f"\nStopping retries: '{err_val}' occurred repeatedly. "
                            "Please explain this error to the user and suggest alternatives.\n"
                        )
                        turn = max_turns  # break outer loop too
                        break

            # append assistant turn and tool results as user message
            messages.append({"role": "assistant", "content": chunk_buf})
            messages.append({"role": "user", "content": f"Tool results:{tool_results_text}\nContinue."})
            full_response += f"\n[Tool results fed back to model]"

        self.ctx.add_message("assistant", full_response)

        # unload model after complex tasks to free RAM
        if task in ("complex", "hardest"):
            self.router.unload_model(model)

        return full_response
