"""Context management: rolling summary, vector memory, session memory."""
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

log = logging.getLogger("ajaxcode.context")

CONFIG_DIR = Path.home() / ".ajaxcode"
MEMORY_DB = CONFIG_DIR / "memory.db"
VECTOR_DIR = CONFIG_DIR / "vector"


def _token_estimate(text: str) -> int:
    """Rough token count: ~4 chars per token."""
    return max(1, len(text) // 4)


class SessionMemory:
    """SQLite-backed cross-session memory."""

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(MEMORY_DB))
        self._init_db()

    def _init_db(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY, value TEXT
            );
            CREATE TABLE IF NOT EXISTS projects (
                path TEXT PRIMARY KEY, summary TEXT, last_used TEXT
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT, content TEXT, created_at TEXT
            );
        """)
        self.conn.commit()

    def set_pref(self, key: str, value: str) -> None:
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
                (key, value),
            )
            self.conn.commit()
        except Exception as e:
            log.error(f"set_pref: {e}")

    def get_pref(self, key: str, default: str = "") -> str:
        try:
            row = self.conn.execute(
                "SELECT value FROM preferences WHERE key=?", (key,)
            ).fetchone()
            return row[0] if row else default
        except Exception:
            return default

    def remember_project(self, path: str, summary: str) -> None:
        try:
            from datetime import datetime
            self.conn.execute(
                "INSERT OR REPLACE INTO projects (path, summary, last_used) VALUES (?,?,?)",
                (path, summary, datetime.now().isoformat()),
            )
            self.conn.commit()
        except Exception as e:
            log.error(f"remember_project: {e}")

    def add_note(self, category: str, content: str) -> None:
        try:
            from datetime import datetime
            self.conn.execute(
                "INSERT INTO notes (category, content, created_at) VALUES (?,?,?)",
                (category, content, datetime.now().isoformat()),
            )
            self.conn.commit()
        except Exception as e:
            log.error(f"add_note: {e}")

    def get_notes(self, category: str = "", limit: int = 20) -> list[dict]:
        try:
            if category:
                rows = self.conn.execute(
                    "SELECT category, content, created_at FROM notes WHERE category=? ORDER BY id DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT category, content, created_at FROM notes ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [{"category": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        except Exception:
            return []


class VectorMemory:
    """ChromaDB vector memory with keyword fallback."""

    def __init__(self) -> None:
        self._client = None
        self._collection = None
        self._fallback: list[dict] = []
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            VECTOR_DIR.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(VECTOR_DIR))
            self._collection = self._client.get_or_create_collection("ajaxcode")
        except Exception as e:
            log.warning(f"ChromaDB unavailable, using keyword fallback: {e}")

    def add(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        if self._collection:
            try:
                self._collection.upsert(
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[metadata or {}],
                )
                return
            except Exception as e:
                log.warning(f"VectorMemory.add chroma error: {e}")
        self._fallback.append({"id": doc_id, "text": text, "meta": metadata or {}})

    def search(self, query: str, n: int = 5) -> list[str]:
        if self._collection:
            try:
                results = self._collection.query(query_texts=[query], n_results=min(n, 5))
                docs = results.get("documents", [[]])[0]
                return docs
            except Exception as e:
                log.warning(f"VectorMemory.search chroma error: {e}")
        # keyword fallback
        q = query.lower()
        scored = [(sum(w in r["text"].lower() for w in q.split()), r["text"])
                  for r in self._fallback]
        scored.sort(reverse=True)
        return [t for _, t in scored[:n] if t]


class ContextManager:
    """Manages rolling conversation context and project state."""

    def __init__(self, context_limit: int = 32000) -> None:
        self.context_limit = context_limit
        self.messages: list[dict] = []
        self.project_summary: str = ""
        self.current_file: str = ""
        self.last_error: str = ""
        self.current_task: str = ""
        self.recent_changes: list[str] = []
        self.vector = VectorMemory()
        self.session = SessionMemory()

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.vector.add(
            f"msg_{len(self.messages)}",
            f"{role}: {content}",
            {"role": role},
        )
        self._maybe_compress()

    def _token_total(self) -> int:
        return sum(_token_estimate(m["content"]) for m in self.messages)

    def _maybe_compress(self) -> None:
        """Compress oldest messages when approaching 80% of limit."""
        limit = self.context_limit
        if self._token_total() < limit * 0.8:
            return
        # keep last 10 messages, summarise the rest
        to_summarise = self.messages[:-10]
        keep = self.messages[-10:]
        if not to_summarise:
            return
        combined = "\n".join(f"{m['role']}: {m['content']}" for m in to_summarise)
        summary = f"[Earlier conversation summary: {combined[:500]}...]"
        self.messages = [{"role": "system", "content": summary}] + keep

    def get_messages(self) -> list[dict]:
        return self.messages.copy()

    def search_memory(self, query: str) -> list[str]:
        return self.vector.search(query, n=3)

    def set_project(self, summary: str, path: str = "") -> None:
        self.project_summary = summary
        if path:
            self.session.remember_project(path, summary)

    def note_change(self, description: str) -> None:
        self.recent_changes.append(description)
        if len(self.recent_changes) > 20:
            self.recent_changes = self.recent_changes[-20:]

    def context_pct(self) -> int:
        return int(self._token_total() / self.context_limit * 100)
