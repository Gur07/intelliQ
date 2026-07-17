"""
core/cache.py
Semantic cache backed by cache.db (SQLite, separate from analytics.db).
Uses sentence-transformers (all-MiniLM-L6-v2) for embeddings.
"""

import hashlib
import json
import pickle
import re
import sqlite3
import time
from typing import Dict, List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

CACHE_DB_PATH              = "cache.db"
CACHE_SIMILARITY_THRESHOLD = 0.90   # >= this → EXACT
CACHE_TTL_SECONDS          = 86400  # 24 h

_conn = sqlite3.connect(CACHE_DB_PATH, check_same_thread=False)
_conn.executescript("""
    CREATE TABLE IF NOT EXISTS cache_entries (
        cache_id         TEXT PRIMARY KEY,
        user_query       TEXT NOT NULL,
        normalized_query TEXT NOT NULL,
        embedding        BLOB NOT NULL,
        generated_sql    TEXT,
        sql_hash         TEXT,
        execution_result TEXT,
        metadata         TEXT,
        query_type       TEXT,
        final_response   TEXT,
        created_at       REAL NOT NULL,
        last_accessed    REAL NOT NULL,
        access_count     INTEGER DEFAULT 1,
        execution_time   REAL DEFAULT 0,
        llm_model        TEXT,
        ttl              REAL DEFAULT 86400
    );
""")
_conn.commit()

_embedder = SentenceTransformer("all-MiniLM-L6-v2")


def embed_query(text: str) -> np.ndarray:
    return _embedder.encode([text], normalize_embeddings=True)[0]


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def normalize_query(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def search_cache(embedding: np.ndarray) -> Optional[Dict]:
    """Return the closest cache entry (with 'similarity' key added), or None if empty."""
    rows = _conn.execute(
        "SELECT cache_id, user_query, normalized_query, embedding, generated_sql, "
        "execution_result, metadata, query_type, final_response, access_count "
        "FROM cache_entries"
    ).fetchall()
    if not rows:
        return None
    best, best_score = None, -1.0
    for row in rows:
        score = cosine_sim(embedding, pickle.loads(row[3]))
        if score > best_score:
            best_score = score
            best = {
                "cache_id":         row[0],
                "user_query":       row[1],
                "normalized_query": row[2],
                "generated_sql":    row[4],
                "execution_result": json.loads(row[5]) if row[5] else None,
                "metadata":         json.loads(row[6]) if row[6] else {},
                "query_type":       row[7],
                "final_response":   row[8],
                "access_count":     row[9],
                "similarity":       score,
            }
    return best


def upsert_cache(
    user_query: str,
    embedding: np.ndarray,
    sql: Optional[str],
    result: Optional[List[Dict]],
    metadata: Dict,
    query_type: str,
    final_response: str,
    execution_time: float,
    reused_cache_id: Optional[str] = None,
    model: str = "gemini-2.5-flash",
):
    """Insert a new cache entry or increment hit count for an EXACT reuse."""
    now = time.time()
    if reused_cache_id:
        _conn.execute(
            "UPDATE cache_entries SET last_accessed=?, access_count=access_count+1, "
            "execution_result=?, execution_time=? WHERE cache_id=?",
            (now, json.dumps(result, default=str), execution_time, reused_cache_id),
        )
    else:
        cache_id = hashlib.md5(user_query.encode()).hexdigest()
        sql_hash = hashlib.sha256(sql.encode()).hexdigest() if sql else ""
        _conn.execute(
            """INSERT OR REPLACE INTO cache_entries
               (cache_id, user_query, normalized_query, embedding, generated_sql, sql_hash,
                execution_result, metadata, query_type, final_response,
                created_at, last_accessed, access_count, execution_time, llm_model, ttl)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
            (
                cache_id, user_query, normalize_query(user_query),
                pickle.dumps(embedding), sql, sql_hash,
                json.dumps(result, default=str) if result else None,
                json.dumps(metadata), query_type, final_response,
                now, now, execution_time, model, CACHE_TTL_SECONDS,
            ),
        )
    _conn.commit()


def cache_stats() -> Dict:
    row = _conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(access_count), 0) FROM cache_entries"
    ).fetchone()
    return {"entries": row[0], "total_hits": row[1]}


def get_all_cache_entries() -> List[Dict]:
    """Return all entries for the sidebar cache browser."""
    rows = _conn.execute(
        "SELECT cache_id, user_query, query_type, access_count, "
        "created_at, last_accessed, execution_time "
        "FROM cache_entries ORDER BY last_accessed DESC"
    ).fetchall()
    return [
        {
            "cache_id":      r[0][:8],
            "user_query":    r[1],
            "query_type":    r[2],
            "access_count":  r[3],
            "created_at":    time.strftime("%Y-%m-%d %H:%M", time.localtime(r[4])),
            "last_accessed": time.strftime("%Y-%m-%d %H:%M", time.localtime(r[5])),
            "exec_ms":       int(r[6] * 1000),
        }
        for r in rows
    ]
