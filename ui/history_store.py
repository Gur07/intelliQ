"""
ui/history_store.py
Small SQLite-backed store for Streamlit chat sessions and turn history.
"""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, List, Optional


DB_PATH = Path("ui_chat_history.db")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row


def _init_db() -> None:
    _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id   TEXT PRIMARY KEY,
            thread_id    TEXT NOT NULL,
            title        TEXT NOT NULL,
            created_at   REAL NOT NULL,
            updated_at   REAL NOT NULL,
            turn_count   INTEGER NOT NULL DEFAULT 0,
            last_query   TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS chat_turns (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id         TEXT NOT NULL,
            turn_index         INTEGER NOT NULL,
            user_query         TEXT NOT NULL,
            assistant_response TEXT NOT NULL,
            sql_query          TEXT,
            sql_result         TEXT,
            cache_decision     TEXT,
            query_type         TEXT,
            similarity         REAL,
            cache_hit          TEXT,
            created_at         REAL NOT NULL,
            FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
        );
        """
    )
    _conn.commit()


_init_db()


def _now() -> float:
    import time

    return time.time()


def _default_title(query: str) -> str:
    compact = " ".join(query.split())
    if len(compact) <= 42:
        return compact
    return compact[:39].rstrip() + "..."


def create_session(title: str = "New chat", thread_id: Optional[str] = None) -> Dict:
    session_id = str(uuid.uuid4())
    thread_id = thread_id or session_id
    now = _now()
    _conn.execute(
        """
        INSERT INTO chat_sessions (session_id, thread_id, title, created_at, updated_at, turn_count, last_query)
        VALUES (?, ?, ?, ?, ?, 0, '')
        """,
        (session_id, thread_id, title, now, now),
    )
    _conn.commit()
    return get_session(session_id) or {}


def list_sessions() -> List[Dict]:
    rows = _conn.execute(
        """
        SELECT session_id, thread_id, title, created_at, updated_at, turn_count, last_query
        FROM chat_sessions
        ORDER BY updated_at DESC, created_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_session(session_id: str) -> Optional[Dict]:
    row = _conn.execute(
        """
        SELECT session_id, thread_id, title, created_at, updated_at, turn_count, last_query
        FROM chat_sessions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    return dict(row) if row else None


def ensure_session(session_id: Optional[str] = None) -> Dict:
    if session_id:
        session = get_session(session_id)
        if session:
            return session
    sessions = list_sessions()
    if sessions:
        return sessions[0]
    return create_session()


def rename_session(session_id: str, title: str) -> None:
    _conn.execute(
        "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE session_id = ?",
        (title, _now(), session_id),
    )
    _conn.commit()


def delete_session(session_id: str) -> None:
    _conn.execute("DELETE FROM chat_turns WHERE session_id = ?", (session_id,))
    _conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
    _conn.commit()


def load_turns(session_id: str) -> List[Dict]:
    rows = _conn.execute(
        """
        SELECT user_query, assistant_response, sql_query, sql_result,
               cache_decision, query_type, similarity, cache_hit, created_at, turn_index
        FROM chat_turns
        WHERE session_id = ?
        ORDER BY turn_index ASC, id ASC
        """,
        (session_id,),
    ).fetchall()

    turns: List[Dict] = []
    for row in rows:
        turns.append(
            {
                "user": row[0],
                "response": row[1],
                "sql_query": row[2],
                "sql_result": json.loads(row[3]) if row[3] else None,
                "cache_decision": row[4],
                "query_type": row[5],
                "similarity": row[6] or 0.0,
                "cache_hit": json.loads(row[7]) if row[7] else None,
                "created_at": row[8],
                "turn_index": row[9],
            }
        )
    return turns


def save_turn(session_id: str, turn: Dict) -> None:
    session = ensure_session(session_id)
    turn_count = int(session.get("turn_count") or 0)
    now = _now()

    cache_hit = turn.get("cache_hit")
    sql_result = turn.get("sql_result")
    if not sql_result and cache_hit:
        sql_result = cache_hit.get("execution_result")

    _conn.execute(
        """
        INSERT INTO chat_turns (
            session_id, turn_index, user_query, assistant_response,
            sql_query, sql_result, cache_decision, query_type,
            similarity, cache_hit, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            turn_count + 1,
            turn.get("user", ""),
            turn.get("response", ""),
            turn.get("sql_query"),
            json.dumps(sql_result, default=str) if sql_result is not None else None,
            turn.get("cache_decision"),
            turn.get("query_type"),
            turn.get("similarity", 0.0),
            json.dumps(cache_hit, default=str) if cache_hit is not None else None,
            now,
        ),
    )

    title = session.get("title") or "New chat"
    if turn_count == 0 and title == "New chat":
        title = _default_title(turn.get("user", "New chat"))

    _conn.execute(
        """
        UPDATE chat_sessions
        SET title = ?, updated_at = ?, turn_count = ?, last_query = ?
        WHERE session_id = ?
        """,
        (title, now, turn_count + 1, turn.get("user", ""), session_id),
    )
    _conn.commit()
