"""
ui/sidebar.py
Renders the left sidebar:
  - App header + stats (hit rate, latency, queries)
  - Schema Explorer (collapsible per table)
  - Cache Stats panel
  - LLM Call Log
"""

import streamlit as st
import pandas as pd

from core.cache import cache_stats, get_all_cache_entries
from core.database import db_stats
from core.rate_limiter import tracker
from ui.components import stat_badge


def render_sidebar():
    with st.sidebar:
        # ── App header ────────────────────────────────────────────────────────
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
                <div style="
                    background:#1E88E5;border-radius:8px;
                    width:36px;height:36px;display:flex;
                    align-items:center;justify-content:center;
                    font-size:18px">🔍</div>
                <div>
                    <div style="font-weight:700;font-size:16px">SQLLens</div>
                    <div style="font-size:11px;color:#888">SQL INTELLIGENCE</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()

        # ── Live metrics ──────────────────────────────────────────────────────
        summary = tracker.summary()
        calls   = tracker.get_calls()
        cstats  = cache_stats()

        total_q = st.session_state.get("total_queries", 0)
        cached  = summary.get("cached", 0)
        hit_rate = f"{int(cached / total_q * 100)}%" if total_q else "—"

        col1, col2, col3 = st.columns(3)
        col1.metric("Hit Rate",  hit_rate)
        col2.metric("Avg ms",    f"{summary['avg_ms']}")
        col3.metric("Queries",   total_q)

        st.divider()

        # ── Schema Explorer ───────────────────────────────────────────────────
        st.markdown("**SCHEMA EXPLORER**")
        dstats = db_stats()

        tables = {
            "customers": {
                "rows":    dstats["customers"],
                "columns": [
                    ("customer_id", "INT"),
                    ("name",        "VARCHAR"),
                    ("region",      "VARCHAR"),
                    ("signup_date", "DATE"),
                ],
            },
            "products": {
                "rows":    dstats["products"],
                "columns": [
                    ("product_id",   "INT"),
                    ("product_name", "VARCHAR"),
                    ("category",     "VARCHAR"),
                    ("unit_price",   "FLOAT"),
                ],
            },
            "sales": {
                "rows":    dstats["sales"],
                "columns": [
                    ("sale_id",     "INT"),
                    ("customer_id", "INT"),
                    ("product_id",  "INT"),
                    ("quantity",    "INT"),
                    ("sale_date",   "DATE"),
                    ("revenue",     "FLOAT"),
                ],
            },
        }

        for table_name, meta in tables.items():
            with st.expander(f"📋 {table_name}  ({meta['rows']:,} rows)"):
                for col_name, col_type in meta["columns"]:
                    st.markdown(
                        f"""
                        <div style="display:flex;justify-content:space-between;
                                    padding:2px 0;font-size:12px">
                            <span style="color:#e2e8f0">{col_name}</span>
                            <span style="color:#64748b">{col_type}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        st.divider()

        # ── Cache stats ───────────────────────────────────────────────────────
        st.markdown("**CACHE**")
        col1, col2 = st.columns(2)
        col1.metric("Entries",    cstats["entries"])
        col2.metric("Total Hits", cstats["total_hits"])

        entries = get_all_cache_entries()
        if entries:
            with st.expander("Browse cache entries"):
                for e in entries[:10]:
                    st.markdown(
                        f"""
                        <div style="
                            border:1px solid #1e293b;border-radius:6px;
                            padding:8px;margin-bottom:6px;font-size:12px">
                            <div style="color:#e2e8f0;margin-bottom:2px">
                                {e['user_query'][:55]}{'…' if len(e['user_query'])>55 else ''}
                            </div>
                            <div style="color:#64748b">
                                {e['query_type']} · {e['access_count']} hits · {e['exec_ms']}ms
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        st.divider()

        # ── LLM call log ──────────────────────────────────────────────────────
        st.markdown("**LLM CALL LOG**")
        if calls:
            icons = {"ok": "✅", "error": "❌", "blocked": "🚫", "cache": "⚡"}
            for c in reversed(calls[-8:]):
                icon = icons.get(c["status"], "🔹")
                st.markdown(
                    f"""
                    <div style="font-size:11px;padding:3px 0;
                                border-bottom:1px solid #1e293b;">
                        {icon} <b>{c['node']}</b>
                        <span style="color:#64748b;float:right">{c['latency_ms']}ms</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No calls yet.")

        st.divider()

        # ── Controls ──────────────────────────────────────────────────────────
        st.markdown("**SYSTEM**")
        if st.button("⚙ Settings", use_container_width=True):
            st.session_state["show_settings"] = True
        if st.button("🗑 Clear history", use_container_width=True):
            st.session_state["messages"] = []
            st.session_state["total_queries"] = 0
            tracker.reset()
            st.rerun()
