from __future__ import annotations
import sqlite3
from urllib.parse import urlparse

class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._conn = self._connect(database_url)

    def _connect(self, database_url: str) -> sqlite3.Connection:
        # supports sqlite:///path
        parsed = urlparse(database_url)
        if parsed.scheme != "sqlite":
            raise ValueError("Only sqlite is supported in this template. Use sqlite:///./data/bot.sqlite")
        path = parsed.path
        if path.startswith("/"):
            # in sqlite url, absolute path comes with leading /
            # allow ./relative via sqlite:///./data/...
            pass
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def execute(self, sql: str, params: tuple = ()):
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def executemany(self, sql: str, seq_of_params):
        cur = self._conn.executemany(sql, seq_of_params)
        self._conn.commit()
        return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        cur = self._conn.execute(sql, params)
        return cur.fetchall()
