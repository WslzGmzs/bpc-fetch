"""Incremental download state: track fetched URLs to avoid re-downloading."""
import sqlite3
from pathlib import Path

DEFAULT_DB = Path.home() / ".local/share/bpc-fetch/history.db"


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""CREATE TABLE IF NOT EXISTS fetched (
        url TEXT PRIMARY KEY,
        domain TEXT,
        title TEXT,
        fetched_at TEXT DEFAULT (datetime('now')),
        path TEXT
    )""")
    conn.commit()
    return conn


def is_fetched(url: str, db_path: Path | None = None) -> bool:
    conn = get_db(db_path)
    row = conn.execute("SELECT 1 FROM fetched WHERE url = ?", (url,)).fetchone()
    conn.close()
    return row is not None


def mark_fetched(url: str, domain: str, title: str, path: str, db_path: Path | None = None):
    conn = get_db(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO fetched (url, domain, title, path) VALUES (?, ?, ?, ?)",
        (url, domain, title, path)
    )
    conn.commit()
    conn.close()


def get_history(domain: str | None = None, limit: int = 50, db_path: Path | None = None) -> list[dict]:
    conn = get_db(db_path)
    if domain:
        rows = conn.execute(
            "SELECT url, domain, title, fetched_at, path FROM fetched WHERE domain = ? ORDER BY fetched_at DESC LIMIT ?",
            (domain, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT url, domain, title, fetched_at, path FROM fetched ORDER BY fetched_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [{"url": r[0], "domain": r[1], "title": r[2], "fetched_at": r[3], "path": r[4]} for r in rows]
