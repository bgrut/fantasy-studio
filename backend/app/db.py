from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from .config import DB_PATH


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS render_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                topic TEXT NOT NULL,
                template_name TEXT NOT NULL,
                status TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                local_output_path TEXT,
                output_url TEXT,
                stdout_log TEXT,
                stderr_log TEXT,
                error_text TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                stage TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        # ── Schema migration: add directorial_controls column if missing ──
        try:
            cols = [
                row[1]
                for row in conn.execute("PRAGMA table_info(render_jobs)").fetchall()
            ]
            if "directorial_controls" not in cols:
                conn.execute(
                    "ALTER TABLE render_jobs ADD COLUMN directorial_controls TEXT"
                )
            if "recipe_name" not in cols:
                conn.execute(
                    "ALTER TABLE render_jobs ADD COLUMN recipe_name TEXT"
                )
            if "source" not in cols:
                # 'queue' (classic create-project flow) vs 'preview' (Studio live)
                conn.execute(
                    "ALTER TABLE render_jobs ADD COLUMN source TEXT"
                )
        except Exception:
            pass  # column already exists or table doesn't exist yet