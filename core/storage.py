"""SQLite persistence for audit history."""
import json
import sqlite3

from .config import DATA_DIR, DB_PATH


def _conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute(
        """CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT, filename TEXT, model TEXT,
            overall REAL, grade TEXT, issues INTEGER, duration_s REAL,
            result TEXT
        )"""
    )
    return con


def save_audit(r: dict) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO audits (created_at, filename, model, overall, grade, issues, duration_s, result)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (r["created_at"], r["filename"], r["model"], r["overall"], r["grade"],
             r["stats"]["issues_total"], r["duration_s"], json.dumps(r)),
        )
        return cur.lastrowid


def list_audits() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, filename, model, overall, grade, issues, duration_s"
            " FROM audits ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_audit(audit_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT id, result FROM audits WHERE id = ?", (audit_id,)).fetchone()
    if not row:
        return None
    data = json.loads(row["result"])
    data["id"] = row["id"]
    return data


def delete_audit(audit_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM audits WHERE id = ?", (audit_id,))
