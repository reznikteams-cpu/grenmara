from __future__ import annotations
from app.storage.db import Database

def ensure_schema(db: Database) -> None:
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
      user_id INTEGER PRIMARY KEY,
      username TEXT,
      first_name TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      last_seen_at TEXT DEFAULT (datetime('now')),
      is_active_subscription INTEGER DEFAULT 0,
      free_messages_used INTEGER DEFAULT 0
    );
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS kb_documents (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_key TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL,
      raw_text TEXT NOT NULL,
      updated_at TEXT DEFAULT (datetime('now'))
    );
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS kb_chunks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      doc_id INTEGER NOT NULL,
      chunk_index INTEGER NOT NULL,
      content TEXT NOT NULL,
      embedding_json TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS broadcasts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      admin_id INTEGER NOT NULL,
      segment TEXT NOT NULL,
      text TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT DEFAULT (datetime('now'))
    );
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS scheduled_pushes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      creator_admin_id INTEGER NOT NULL,
      segment TEXT NOT NULL,
      text TEXT NOT NULL,
      run_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT DEFAULT (datetime('now'))
    );
    """)
