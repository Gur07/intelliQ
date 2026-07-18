"""
ui/components.py
Reusable Streamlit widgets used across sidebar and chat panels.
"""

import json

import pandas as pd
import streamlit as st


def stat_badge(label: str, value, color: str = "#1E88E5"):
    """Small metric card used in the sidebar."""
    st.markdown(
        f"""
        <div style="
            background:{color}18;
            border:1px solid {color}44;
            border-radius:8px;
            padding:8px 12px;
            margin-bottom:8px;
        ">
            <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.5px">
                {label}
            </div>
            <div style="font-size:20px;font-weight:700;color:{color}">
                {value}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def execution_trace(steps: list):
    """
    Render the IntelliQ-style execution trace box.
    steps: list of strings, each prefixed with an emoji by the caller.
    """
    if not steps:
        return
    items_html = "".join(
        f'<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px;">'
        f'<span style="color:#1e88e5;margin-top:1px">•</span>'
        f'<span style="font-family:ui-monospace, SFMono-Regular, Menlo, monospace;font-size:12px;color:#334155">{s}</span>'
        f"</div>"
        for s in steps
    )
    st.markdown(
        f"""
        <div style="
            background:white;
            border:1px solid #dbe5f0;
            border-radius:16px;
            padding:12px 16px;
            margin-bottom:12px;
            box-shadow:0 8px 22px rgba(15,23,42,0.04);
        ">
            <div style="font-size:10px;color:#64748b;letter-spacing:1px;
                        text-transform:uppercase;margin-bottom:8px;font-weight:700">
                Execution trace
            </div>
            {items_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def sql_block(sql: str, dialect: str = "SQLite"):
    """Render a formatted SQL code block with a dialect badge."""
    with st.expander(f"SQL query ({dialect})", expanded=True):
        st.code(sql, language="sql")


def render_result_table(rows: list):
    if not rows:
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_json_preview(value, label: str = "Raw payload"):
    if value is None:
        return
    pretty = json.dumps(value, default=str, indent=2)
    with st.expander(label):
        st.code(pretty, language="json")


def cache_badge(decision: str, similarity: float):
    """Show a coloured badge indicating cache status."""
    colours = {"EXACT": "#22c55e", "PARTIAL": "#f59e0b", "MISS": "#6366f1"}
    colour  = colours.get(decision, "#888")
    st.markdown(
        f"""
        <div style="display:inline-flex;align-items:center;gap:8px;
                    background:{colour}14;border:1px solid {colour}33;
                    border-radius:20px;padding:4px 12px;margin-bottom:10px">
            <span style="width:7px;height:7px;border-radius:50%;
                         background:{colour};display:inline-block"></span>
            <span style="font-size:12px;font-weight:600;color:{colour}">
                {decision}
            </span>
            <span style="font-size:11px;color:#64748b">sim={similarity:.2f}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def findings_card(findings: list):
    """Render a styled findings list."""
    items = "".join(
        f'<li style="margin-bottom:6px;color:#cbd5e1">{f}</li>'
        for f in findings
    )
    st.markdown(
        f'<ul style="padding-left:18px;margin:0">{items}</ul>',
        unsafe_allow_html=True,
    )
