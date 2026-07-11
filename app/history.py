"""辨識歷史（SQLite）。保留最近 200 筆，超出自動汰舊。"""
import sqlite3
import threading
import time

KEEP = 200


class History:
    def __init__(self, db_path):
        self._path = str(db_path)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS history ("
                      "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                      "ts REAL, text TEXT, engine TEXT)")

    def _conn(self):
        return sqlite3.connect(self._path)

    def add(self, text: str, engine: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO history (ts, text, engine) VALUES (?,?,?)",
                      (time.time(), text, engine))
            c.execute("DELETE FROM history WHERE id NOT IN "
                      "(SELECT id FROM history ORDER BY id DESC LIMIT ?)", (KEEP,))

    def list(self, limit: int = 200) -> list[dict]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT ts, text, engine FROM history "
                             "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts": r[0], "text": r[1], "engine": r[2]} for r in rows]

    def clear(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM history")
