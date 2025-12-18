from __future__ import annotations

import json
import math
from typing import Optional
from app.storage.db import Database


class Repo:
    def __init__(self, db: Database):
        self.db = db

    # --- users ---
    def upsert_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        self.db.execute("""
        INSERT INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          username=excluded.username,
          first_name=excluded.first_name,
          last_seen_at=datetime('now');
        """, (user_id, username, first_name))

    def get_user(self, user_id: int):
        rows = self.db.query("SELECT * FROM users WHERE user_id=?", (user_id,))
        return rows[0] if rows else None

    def inc_free_used(self, user_id: int) -> None:
        self.db.execute(
            "UPDATE users SET free_messages_used=free_messages_used+1, last_seen_at=datetime('now') WHERE user_id=?",
            (user_id,),
        )

    def set_subscription(self, user_id: int, is_active: bool) -> None:
        self.db.execute("UPDATE users SET is_active_subscription=? WHERE user_id=?", (1 if is_active else 0, user_id))

    # --- messages ---
    def add_message(self, user_id: int, role: str, content: str) -> None:
        self.db.execute("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)", (user_id, role, content))

    def get_recent_messages(self, user_id: int, limit: int = 20):
        return self.db.query(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )[::-1]

    def clear_messages(self, user_id: int) -> None:
        self.db.execute("DELETE FROM messages WHERE user_id=?", (user_id,))

    # --- kb ---
    def upsert_document(self, source_key: str, title: str, raw_text: str) -> int:
        self.db.execute("""
        INSERT INTO kb_documents (source_key, title, raw_text)
        VALUES (?, ?, ?)
        ON CONFLICT(source_key) DO UPDATE SET
          title=excluded.title,
          raw_text=excluded.raw_text,
          updated_at=datetime('now');
        """, (source_key, title, raw_text))
        doc = self.db.query("SELECT id FROM kb_documents WHERE source_key=?", (source_key,))[0]
        return int(doc["id"])

    def replace_chunks(self, doc_id: int, chunks: list[tuple[int, str, list[float]]]) -> None:
        # chunks: (chunk_index, content, embedding)
        self.db.execute("DELETE FROM kb_chunks WHERE doc_id=?", (doc_id,))
        self.db.executemany(
            "INSERT INTO kb_chunks (doc_id, chunk_index, content, embedding_json) VALUES (?, ?, ?, ?)",
            [(doc_id, idx, content, json.dumps(emb)) for idx, content, emb in chunks],
        )

    def get_all_chunks(self):
        rows = self.db.query("SELECT id, content, embedding_json FROM kb_chunks")
        out = []
        for r in rows:
            out.append((int(r["id"]), r["content"], json.loads(r["embedding_json"])))
        return out

    # --- NEW: read raw document text (needed for "Символизм" exact phrasing/questions) ---
    def get_document_raw_text_by_title(self, title: str) -> str | None:
        """
        Возвращает документ по title без учета регистра.

        В gdocs_sources админы иногда задают title как "Symbolism" или
        "Символизм" с заглавной буквы, а при поиске мы используем нижний регистр
        ("symbolism"). Поэтому сравниваем в LOWER(...) чтобы не зависеть от
        регистра и лишних пробелов.
        """
        rows = self.db.query(
            """
            SELECT raw_text
            FROM kb_documents
            WHERE lower(title) = lower(?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (title.strip(),),
        )
        if not rows:
            return None
        return rows[0]["raw_text"]

    def get_document_raw_text_by_source_key(self, source_key: str) -> str | None:
        rows = self.db.query(
            "SELECT raw_text FROM kb_documents WHERE source_key=? LIMIT 1",
            (source_key,),
        )
        if not rows:
            return None
        return rows[0]["raw_text"]

    def get_document_raw_text_by_source_key_prefix(self, prefix: str) -> str | None:
        # e.g. prefix "gdocs:...:" if you want
        rows = self.db.query(
            "SELECT raw_text FROM kb_documents WHERE source_key LIKE ? ORDER BY id DESC LIMIT 1",
            (prefix + "%",),
        )
        if not rows:
            return None
        return rows[0]["raw_text"]

    # --- NEW: semantic KB search over chunks ---
    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return -1.0
        dot = 0.0
        na = 0.0
        nb = 0.0
        for i in range(len(a)):
            dot += a[i] * b[i]
            na += a[i] * a[i]
            nb += b[i] * b[i]
        if na <= 0.0 or nb <= 0.0:
            return -1.0
        return dot / (math.sqrt(na) * math.sqrt(nb))

    def kb_search(self, query_embedding: list[float], top_k: int = 3) -> list[dict]:
        """
        Returns top_k chunks by cosine similarity.
        Caller is responsible for generating query_embedding (OpenAI embeddings).
        """
        chunks = self.get_all_chunks()
        scored: list[tuple[float, int, str]] = []
        for chunk_id, content, emb in chunks:
            sim = self._cosine(query_embedding, emb)
            scored.append((sim, chunk_id, content))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sim, chunk_id, content in scored[:top_k]:
            out.append({"chunk_id": chunk_id, "score": float(sim), "content": content})
        return out

    # --- broadcasts / pushes ---
    def list_users_by_segment(self, segment: str) -> list[int]:
        if segment == "all":
            rows = self.db.query("SELECT user_id FROM users")
        elif segment == "active":
            rows = self.db.query("SELECT user_id FROM users WHERE is_active_subscription=1")
        elif segment == "inactive":
            rows = self.db.query("SELECT user_id FROM users WHERE is_active_subscription=0")
        elif segment == "dormant_7d":
            rows = self.db.query("SELECT user_id FROM users WHERE last_seen_at < datetime('now','-7 day')")
        else:
            rows = self.db.query("SELECT user_id FROM users")
        return [int(r["user_id"]) for r in rows]

    def create_broadcast(self, admin_id: int, segment: str, text: str) -> int:
        self.db.execute("INSERT INTO broadcasts (admin_id, segment, text) VALUES (?, ?, ?)", (admin_id, segment, text))
        row = self.db.query("SELECT last_insert_rowid() AS id")[0]
        return int(row["id"])

    def create_scheduled_push(self, admin_id: int, segment: str, text: str, run_at_iso: str) -> int:
        self.db.execute(
            "INSERT INTO scheduled_pushes (creator_admin_id, segment, text, run_at) VALUES (?, ?, ?, ?)",
            (admin_id, segment, text, run_at_iso),
        )
        row = self.db.query("SELECT last_insert_rowid() AS id")[0]
        return int(row["id"])

    def get_due_pushes(self):
        return self.db.query("""
          SELECT * FROM scheduled_pushes
          WHERE status='pending' AND run_at <= datetime('now')
          ORDER BY id ASC
        """)

    def mark_push_sent(self, push_id: int) -> None:
        self.db.execute("UPDATE scheduled_pushes SET status='sent' WHERE id=?", (push_id,))
