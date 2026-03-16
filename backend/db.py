from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DB_PATH = Path(__file__).resolve().parent.parent / "artifacts" / "labpilot_app.db"


def ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_runs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                dataset_path TEXT NOT NULL,
                target_column TEXT NOT NULL,
                features_json TEXT,
                model_path TEXT,
                meta_path TEXT,
                metrics_json TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_runs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                strategy TEXT NOT NULL,
                dataset_path TEXT NOT NULL,
                model_path TEXT NOT NULL,
                budget INTEGER NOT NULL,
                n_init INTEGER NOT NULL,
                seed INTEGER NOT NULL,
                output_path TEXT,
                summary_json TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                conversation_id TEXT,
                dataset_path TEXT NOT NULL,
                model_path TEXT NOT NULL,
                budget INTEGER NOT NULL,
                top_k INTEGER NOT NULL,
                use_llm INTEGER NOT NULL DEFAULT 0,
                use_tavily INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                best_observed_yield REAL,
                steps_completed INTEGER NOT NULL DEFAULT 0,
                last_recommendation_json TEXT,
                last_reasoning_json TEXT,
                last_evidence_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Backward-compatible migration for existing DBs created before conversation linkage.
        session_cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "conversation_id" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN conversation_id TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                num_rows INTEGER,
                num_cols INTEGER,
                columns_json TEXT,
                target_candidates_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_results (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                recommendation_json TEXT,
                observed_yield REAL NOT NULL,
                notes TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
            """
        )


@contextmanager
def get_conn() -> Iterable[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def fetch_all(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(r) for r in rows]


def fetch_one(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(query, params).fetchone()
    return row_to_dict(row) if row else None


def exec_sql(query: str, params: tuple = ()) -> None:
    with get_conn() as conn:
        conn.execute(query, params)


def dumps_json(value: Any) -> str:
    return json.dumps(value) if value is not None else ""

