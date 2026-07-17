"""
ui/chat.py
Renders the main chat panel:
  - Conversation history (user + assistant bubbles)
  - Execution trace block (node steps)
  - SQL block display
  - Input box at the bottom
"""

import json
import streamlit as st

from core.schemas import RESET
from core.rate_limiter import tracker
from ui.components import cache_badge, execution_trace, sql_block


# Suggested starter queries shown on an empty chat
EXAMPLE_QUERIES = [
    "Show me the top 10 customers by revenue",
    "Which product category performs best and why?",
    "Forecast revenue for the next 7 days",
    "Compare sales across all regions this year",
]


def _render_user_bubble(text: str):
    st.markdown(
        f"""
        <div style="display:flex;justify-content:flex-end;margin:8px 0">
            <div style="
                background:#1E88E5;color:white;
                border-radius:18px 18px 4px 18px;
                padding:10px 16px;max-width:70%;font-size:14px;
                line-height:1.5">
                {text}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_assistant_bubble(content: str):
    st.markdown(
        f"""
        <div style="display:flex;justify-content:flex-start;margin:8px 0">
            <div style="
                background:#1e293b;color:#e2e8f0;
                border-radius:18px 18px 18px 4px;
                padding:10px 16px;max-width:80%;font-size:14px;
                line-height:1.6">
                {content}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _build_trace_steps(turn: dict) -> list:
    """Build the execution trace step list from a completed turn's metadata."""
    steps = []
    decision = turn.get("cache_decision", "MISS")
    qt       = turn.get("query_type", "")
    sim      = turn.get("similarity", 0.0)

    steps.append(f"Cache lookup: similarity={sim:.3f}  →  {decision}")

    if decision == "EXACT":
        steps.append("Serving cached response (no LLM engine call needed)")
        return steps

    if qt in ("irrelevant", "error"):
        steps.append(f"Query classified as: {qt}")
        return steps

    steps.append(f"Query classified as: {qt}")

    if turn.get("sql_query"):
        tables = [t for t in ["customers", "products", "sales"]
                  if t in turn["sql_query"]]
        steps.append(f"Schema lookup: resolved {', '.join(tables)} table(s)")
        if "JOIN" in turn["sql_query"].upper():
            steps.append("Join logic identified: "
                         + turn["sql_query"].upper().split("JOIN")[1].split("ON")[0].strip()[:40])
        rows = len(turn.get("sql_result") or [])
        steps.append(f"Query executed: {rows} row(s) returned")

    if qt == "analytical":
        steps.append("Analytical engine: pattern interpretation complete")
    elif qt == "predictive":
        steps.append("Predictive engine: linear forecast computed")

    return steps


def render_chat(graph):
    """Main chat rendering function. Called from app.py."""

    # ── Empty state — show example queries ───────────────────────────────────
    if not st.session_state.get("messages"):
        st.markdown(
            """
            <div style="text-align:center;padding:40px 0 20px">
                <div style="font-size:28px;font-weight:700;margin-bottom:8px">
                    Ask SQLLens about your data
                </div>
                <div style="color:#64748b;font-size:14px">
                    Natural language → SQL → Insight
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, q in enumerate(EXAMPLE_QUERIES):
            if cols[i % 2].button(q, use_container_width=True, key=f"eg_{i}"):
                st.session_state["pending_query"] = q
                st.rerun()

    # ── Conversation history ──────────────────────────────────────────────────
    for turn in st.session_state.get("messages", []):
        _render_user_bubble(turn["user"])

        # Execution trace
        if turn.get("cache_decision"):
            steps = _build_trace_steps(turn)
            execution_trace(steps)

        # Cache badge
        if turn.get("cache_decision"):
            sim = turn.get("similarity", 0.0)
            cache_badge(turn["cache_decision"], sim)

        # SQL block
        if turn.get("sql_query") and turn.get("cache_decision") != "EXACT":
            sql_block(turn["sql_query"])

        # Assistant response
        _render_assistant_bubble(turn["response"])

    # ── Input box (pinned to bottom) ─────────────────────────────────────────
    st.markdown("<div style='height:80px'></div>", unsafe_allow_html=True)

    with st.container():
        col_input, col_btn = st.columns([9, 1])

        pending = st.session_state.pop("pending_query", None)

        with col_input:
            user_input = st.chat_input(
                "Ask SQLLens about your data...",
                key="chat_input",
            )

        # Handle both typed input and example-button clicks
        query = user_input or pending
        if query:
            _handle_query(query, graph)


def _handle_query(query: str, graph):
    """Invoke the agent graph and store the result in session state."""
    thread_id = st.session_state.get("thread_id", "main")
    config    = {"configurable": {"thread_id": thread_id}}

    with st.spinner("Thinking..."):
        result = graph.invoke({"user_query": query, **RESET}, config=config)

    # Gather metadata for trace rendering
    turn = {
        "user":           query,
        "response":       result.get("final_response", "No response."),
        "cache_decision": result.get("cache_decision"),
        "query_type":     result.get("query_type"),
        "sql_query":      result.get("sql_query"),
        "sql_result":     result.get("sql_result"),
        "similarity":     result.get("cache_hit", {}).get("similarity", 0.0) if result.get("cache_hit") else 0.0,
    }

    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    st.session_state["messages"].append(turn)
    st.session_state["total_queries"] = st.session_state.get("total_queries", 0) + 1

    st.rerun()
