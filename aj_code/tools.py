"""All tools for AJax Code — file, git, web, terminal, code, project."""
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import psutil
import requests

log_dir = Path.home() / ".ajaxcode" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(log_dir / "tools.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("ajaxcode.tools")

Result = dict[str, Any]


def _ok(result: Any) -> Result:
    return {"success": True, "result": result, "error": None}


def _err(error: str) -> Result:
    log.error(error)
    return {"success": False, "result": None, "error": error}


class ToolKit:
    # ── FILE TOOLS ─────────────────────────────────────────────────────────

    def read_file(self, path: str) -> Result:
        try:
            p = Path(path).expanduser().resolve()
            content = p.read_text(encoding="utf-8", errors="replace")
            log.info(f"read_file: {p} ({len(content)} chars)")
            return _ok(content)
        except Exception as e:
            return _err(f"read_file({path}): {e}")

    def write_file(self, path: str, content: str) -> Result:
        try:
            p = Path(path).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            log.info(f"write_file: {p} ({len(content)} chars)")
            return _ok(f"Written {len(content)} chars to {p}")
        except Exception as e:
            return _err(f"write_file({path}): {e}")

    def edit_file(self, path: str, old: str, new: str) -> Result:
        try:
            p = Path(path).expanduser().resolve()
            content = p.read_text(encoding="utf-8", errors="replace")
            if old not in content:
                return _err(f"edit_file: string not found in {path}")
            updated = content.replace(old, new, 1)
            p.write_text(updated, encoding="utf-8")
            log.info(f"edit_file: {p}")
            return _ok(f"Replaced 1 occurrence in {p}")
        except Exception as e:
            return _err(f"edit_file({path}): {e}")

    def delete_file(self, path: str) -> Result:
        try:
            p = Path(path).expanduser().resolve()
            if not p.exists():
                return _err(f"delete_file: {path} does not exist")
            p.unlink()
            log.info(f"delete_file: {p}")
            return _ok(f"Deleted {p}")
        except Exception as e:
            return _err(f"delete_file({path}): {e}")

    def list_files(self, path: str = ".", pattern: str = "*") -> Result:
        try:
            p = Path(path).expanduser().resolve()
            files = sorted(str(f.relative_to(p)) for f in p.rglob(pattern)
                           if f.is_file() and ".git" not in f.parts)
            return _ok(files)
        except Exception as e:
            return _err(f"list_files({path}): {e}")

    def search_in_files(self, query: str, path: str = ".") -> Result:
        try:
            p = Path(path).expanduser().resolve()
            results = []
            for f in p.rglob("*"):
                if not f.is_file() or ".git" in f.parts:
                    continue
                try:
                    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                    for i, line in enumerate(lines, 1):
                        if query.lower() in line.lower():
                            results.append(f"{f.relative_to(p)}:{i}: {line.strip()}")
                except Exception:
                    pass
            return _ok(results)
        except Exception as e:
            return _err(f"search_in_files({query}): {e}")

    def create_directory(self, path: str) -> Result:
        try:
            p = Path(path).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            return _ok(f"Created {p}")
        except Exception as e:
            return _err(f"create_directory({path}): {e}")

    # ── GIT TOOLS ──────────────────────────────────────────────────────────

    def _git(self, args: list[str], cwd: str | None = None) -> Result:
        try:
            r = subprocess.run(
                ["git"] + args,
                capture_output=True, text=True,
                cwd=cwd or str(Path.cwd()),
                timeout=30,
            )
            output = r.stdout + r.stderr
            if r.returncode != 0:
                return _err(output.strip())
            return _ok(output.strip())
        except Exception as e:
            return _err(str(e))

    def git_status(self) -> Result:
        return self._git(["status"])

    def git_diff(self) -> Result:
        return self._git(["diff"])

    def git_add(self, files: list[str] | str) -> Result:
        if isinstance(files, str):
            files = [files]
        return self._git(["add"] + files)

    def git_commit(self, message: str) -> Result:
        return self._git(["commit", "-m", message])

    def git_push(self) -> Result:
        return self._git(["push"])

    def git_pull(self) -> Result:
        return self._git(["pull"])

    def git_log(self, n: int = 10) -> Result:
        return self._git(["log", f"-{n}", "--oneline"])

    def git_branch(self, name: str | None = None, switch: bool = False) -> Result:
        if name and switch:
            return self._git(["checkout", "-b", name])
        elif name:
            return self._git(["branch", name])
        return self._git(["branch", "-a"])

    def git_clone(self, url: str, path: str) -> Result:
        return self._git(["clone", url, path])

    # ── TERMINAL TOOLS ─────────────────────────────────────────────────────

    def run_command(self, cmd: str, cwd: str | None = None) -> Result:
        try:
            proc = subprocess.run(
                cmd, shell=True, text=True, capture_output=True,
                cwd=cwd or str(Path.cwd()), timeout=120,
            )
            output = proc.stdout + proc.stderr
            log.info(f"run_command: {cmd!r} → exit {proc.returncode}")
            return {
                "success": proc.returncode == 0,
                "result": output.strip(),
                "error": None if proc.returncode == 0 else output.strip(),
                "exit_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return _err(f"Command timed out: {cmd}")
        except Exception as e:
            return _err(str(e))

    def install_package(self, name: str, manager: str = "pip") -> Result:
        managers = {
            "pip":  [sys.executable, "-m", "pip", "install", "--break-system-packages", name],
            "npm":  ["npm", "install", "-g", name],
            "cargo": ["cargo", "install", name],
        }
        if manager not in managers:
            return _err(f"Unknown package manager: {manager}")
        try:
            proc = subprocess.run(managers[manager], capture_output=True, text=True, timeout=120)
            return _ok(proc.stdout + proc.stderr) if proc.returncode == 0 else _err(proc.stderr)
        except Exception as e:
            return _err(str(e))

    def check_command_exists(self, cmd: str) -> Result:
        try:
            proc = subprocess.run(["which", cmd], capture_output=True, text=True)
            exists = proc.returncode == 0
            return _ok({"exists": exists, "path": proc.stdout.strip()})
        except Exception as e:
            return _err(str(e))

    # ── WEB TOOLS ──────────────────────────────────────────────────────────

    def web_search(self, query: str) -> Result:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            formatted = [
                {"title": r["title"], "url": r["href"], "snippet": r["body"]}
                for r in results
            ]
            log.info(f"web_search: {query!r} → {len(formatted)} results")
            return _ok(formatted)
        except Exception as e:
            return _err(f"web_search: {e}")

    def fetch_url(self, url: str) -> Result:
        try:
            headers = {"User-Agent": "AJaxCode/1.0"}
            r = requests.get(url, headers=headers, timeout=15)
            # strip HTML tags for readable text
            text = re.sub(r"<[^>]+>", "", r.text)
            text = re.sub(r"\s+", " ", text).strip()
            return _ok(text[:5000])  # cap at 5k chars
        except Exception as e:
            return _err(f"fetch_url({url}): {e}")

    def search_docs(self, query: str, framework: str = "") -> Result:
        full_query = f"{framework} documentation {query}" if framework else f"documentation {query}"
        return self.web_search(full_query)

    def download_file(self, url: str, path: str) -> Result:
        try:
            p = Path(path).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(url, stream=True, timeout=60)
            with open(p, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return _ok(f"Downloaded to {p}")
        except Exception as e:
            return _err(f"download_file({url}): {e}")

    # ── CODE TOOLS ─────────────────────────────────────────────────────────

    def run_python(
        self,
        code: str | None = None,
        path: str | None = None,
        cmd: str | None = None,
    ) -> Result:
        """Execute Python code, a .py file, or a shell command string.

        Priority: cmd > path > code
        """
        try:
            if cmd is not None:
                # run as shell command directly
                return self.run_command(cmd)
            elif path is not None:
                p = Path(path).expanduser().resolve()
                proc = subprocess.run(
                    [sys.executable, str(p)],
                    capture_output=True, text=True, timeout=30,
                )
            elif code is not None:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                    f.write(code)
                    tmp = f.name
                proc = subprocess.run(
                    [sys.executable, tmp],
                    capture_output=True, text=True, timeout=30,
                )
                Path(tmp).unlink(missing_ok=True)
            else:
                return _err("run_python: provide 'code', 'path', or 'cmd'")

            output = proc.stdout + proc.stderr
            return {
                "success": proc.returncode == 0,
                "result": output.strip(),
                "error": proc.stderr.strip() if proc.returncode != 0 else None,
                "exit_code": proc.returncode,
            }
        except Exception as e:
            return _err(str(e))

    def run_javascript(self, code: str) -> Result:
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(code)
                tmp = f.name
            proc = subprocess.run(["node", tmp], capture_output=True, text=True, timeout=30)
            Path(tmp).unlink(missing_ok=True)
            return _ok(proc.stdout + proc.stderr) if proc.returncode == 0 else _err(proc.stderr)
        except Exception as e:
            return _err(str(e))

    def run_bash(self, code: str) -> Result:
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(code)
                tmp = f.name
            proc = subprocess.run(["bash", tmp], capture_output=True, text=True, timeout=60)
            Path(tmp).unlink(missing_ok=True)
            return _ok(proc.stdout + proc.stderr) if proc.returncode == 0 else _err(proc.stderr)
        except Exception as e:
            return _err(str(e))

    def lint_code(self, path: str) -> Result:
        p = Path(path)
        ext = p.suffix.lower()
        if ext == ".py":
            return self.run_command(f"python3 -m py_compile {path} && echo OK")
        elif ext in (".js", ".ts"):
            result = self.check_command_exists("eslint")
            if result["result"]["exists"]:
                return self.run_command(f"eslint {path}")
        return _ok("No linter configured for this file type")

    def format_code(self, path: str) -> Result:
        p = Path(path)
        ext = p.suffix.lower()
        if ext == ".py":
            result = self.check_command_exists("black")
            if result.get("result", {}).get("exists"):
                return self.run_command(f"black {path}")
            return self.run_command(f"autopep8 --in-place {path}")
        elif ext in (".js", ".ts", ".json"):
            return self.run_command(f"prettier --write {path}")
        return _ok("No formatter configured for this file type")

    def find_syntax_errors(self, code: str, language: str = "python") -> Result:
        if language == "python":
            try:
                import ast
                ast.parse(code)
                return _ok("No syntax errors found")
            except SyntaxError as e:
                return _err(f"SyntaxError on line {e.lineno}: {e.msg}")
        return _ok("Syntax check not available for this language")

    # ── PROJECT TOOLS ──────────────────────────────────────────────────────

    def scan_project(self, path: str = ".") -> Result:
        try:
            p = Path(path).expanduser().resolve()
            tree = []
            langs: set[str] = set()
            entry_points = []
            EXT_LANG = {
                ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
                ".go": "Go", ".rs": "Rust", ".java": "Java", ".cpp": "C++",
                ".c": "C", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
            }
            deps = {}

            for f in sorted(p.rglob("*")):
                if any(part.startswith(".") or part in ("node_modules", "__pycache__", "dist", "build")
                       for part in f.parts):
                    continue
                if f.is_file():
                    rel = str(f.relative_to(p))
                    tree.append(rel)
                    lang = EXT_LANG.get(f.suffix.lower())
                    if lang:
                        langs.add(lang)
                    if f.name in ("main.py", "app.py", "index.js", "main.go", "main.rs"):
                        entry_points.append(rel)
                    if f.name == "requirements.txt":
                        try:
                            deps["python"] = f.read_text().splitlines()
                        except Exception:
                            pass
                    if f.name == "package.json":
                        try:
                            import json
                            pkg = json.loads(f.read_text())
                            deps["npm"] = list(pkg.get("dependencies", {}).keys())
                        except Exception:
                            pass

            return _ok({
                "root": str(p),
                "files": tree[:200],
                "languages": sorted(langs),
                "entry_points": entry_points,
                "dependencies": deps,
            })
        except Exception as e:
            return _err(f"scan_project: {e}")

    def get_project_summary(self) -> Result:
        scan = self.scan_project()
        if not scan["success"]:
            return scan
        data = scan["result"]
        langs = ", ".join(data["languages"]) or "unknown"
        files = len(data["files"])
        entries = ", ".join(data["entry_points"]) or "none"
        summary = (
            f"Project at {data['root']}: {files} files, "
            f"languages: {langs}, entry points: {entries}."
        )
        return _ok(summary)

    def find_function(self, name: str, path: str = ".") -> Result:
        return self.search_in_files(f"def {name}", path)

    def find_usages(self, name: str, path: str = ".") -> Result:
        return self.search_in_files(name, path)
