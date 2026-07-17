"""
core/database.py
Handles the analytics SQLite database (analytics.db).
Contains: connection, table creation, seed data, SQL executor, schema loader.
"""

import json
import re
import sqlite3
from typing import Dict, List

import numpy as np

ANALYTICS_DB_PATH = "analytics.db"
DESTRUCTIVE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|REPLACE|CREATE)\b",
    re.IGNORECASE,
)

# Single shared connection — check_same_thread=False for Streamlit's threading
_conn = sqlite3.connect(ANALYTICS_DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row


def seed():
    """Create tables and insert sample data. Idempotent — safe to call on every startup."""
    _conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            region      TEXT NOT NULL,
            signup_date TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            product_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            category     TEXT NOT NULL,
            unit_price   REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sales (
            sale_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
            product_id  INTEGER NOT NULL REFERENCES products(product_id),
            quantity    INTEGER NOT NULL,
            sale_date   TEXT NOT NULL,
            revenue     REAL NOT NULL
        );
    """)

    if _conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] > 0:
        return  # already seeded

    rng = np.random.default_rng(42)
    regions = ["North", "South", "East", "West"]
    for i in range(1, 41):
        _conn.execute(
            "INSERT INTO customers (name, region, signup_date) VALUES (?,?,?)",
            (f"Customer {i}", regions[i % 4],
             f"202{rng.integers(2,5)}-{rng.integers(1,13):02d}-01"),
        )

    catalog = [
        ("Wireless Mouse", "Electronics", 45.00),
        ("USB-C Hub",      "Electronics", 89.00),
        ("T-Shirt",        "Apparel",     22.00),
        ("Hoodie",         "Apparel",     58.00),
        ("Desk Lamp",      "Home",        39.00),
        ("Mug",            "Home",        14.00),
        ("Coffee Beans",   "Grocery",     18.00),
        ("Green Tea",      "Grocery",     12.00),
    ]
    product_ids = []
    for name, cat, price in catalog:
        cur = _conn.execute(
            "INSERT INTO products (product_name, category, unit_price) VALUES (?,?,?)",
            (name, cat, price),
        )
        product_ids.append((cur.lastrowid, price))

    for day in range(365):
        date = f"2024-{((day // 30) + 1):02d}-{((day % 30) + 1):02d}"
        for _ in range(int(rng.integers(2, 8))):
            cid = int(rng.integers(1, 41))
            ppid, price = product_ids[int(rng.integers(0, len(product_ids)))]
            qty = int(rng.integers(1, 5))
            _conn.execute(
                "INSERT INTO sales (customer_id, product_id, quantity, sale_date, revenue) VALUES (?,?,?,?,?)",
                (cid, ppid, qty, date, round(price * qty, 2)),
            )

    _conn.commit()


def load_schema() -> str:
    """Read table/column info from analytics.db and return a formatted string for LLM prompts."""
    tables = [
        r[0]
        for r in _conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    lines = []
    for table in tables:
        cols = _conn.execute(f"PRAGMA table_info({table})").fetchall()
        lines.append(f"TABLE: {table}")
        for col in cols:
            pk_tag = "  PRIMARY KEY" if col[5] else ""
            nn_tag = "  NOT NULL" if col[3] else ""
            lines.append(f"  {col[1]}  {col[2]}{pk_tag}{nn_tag}")
        lines.append("")
    lines.append(
        "IMPORTANT:\n"
        "  - revenue and sale_date are columns on the SALES table ONLY.\n"
        "  - Use SQLite syntax: strftime('%Y-%m', sale_date) for monthly grouping.\n"
        "  - For follow-up questions, AMEND the previous SQL shown — do not rewrite from scratch."
    )
    return "\n".join(lines)


def is_safe(sql: str) -> bool:
    return not bool(DESTRUCTIVE_RE.search(sql))


def run_sql(sql: str) -> List[Dict]:
    """Execute a SELECT query and return up to 100 rows as a list of dicts."""
    cur = _conn.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchmany(100)]
    return json.loads(json.dumps(rows, default=str))


def db_stats() -> Dict:
    """Return row counts for the sidebar."""
    return {
        "customers": _conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "products":  _conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "sales":     _conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
    }
