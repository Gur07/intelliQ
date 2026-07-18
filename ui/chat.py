"""
ui/chat.py
Renders the main chat panel:
  - Conversation history
  - Execution trace block
  - SQL block display
  - Result table display
  - Input box at the bottom
"""

import streamlit as st

from core.schemas import RESET
from ui.components import (
    cache_badge,
    execution_trace,
    render_json_preview,
    render_result_table,
    section_title,
    sql_block,
)
from ui.history_store import load_turns, save_turn


def _build_trace_steps(turn: dict) -> list:
    """Build the execution trace step list from a completed turn's metadata."""
    steps = []
    decision = turn.get("cache_decision", "MISS")
    qt       = turn.get("query_type", "")
    sim      = turn.get("similarity", 0.0)

    steps.append(f"Cache lookup: similarity={sim:.3f} -> {decision}")

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


def _render_turn(turn: dict):
    with st.chat_message("user"):
        st.markdown(turn["user"])

    with st.chat_message("assistant"):
        st.markdown(turn["response"])

        steps = _build_trace_steps(turn)
        if steps:
            section_title("Execution trace")
            execution_trace(steps)

        if turn.get("cache_decision"):
            cache_badge(turn["cache_decision"], turn.get("similarity", 0.0))

        sql_query = turn.get("sql_query")
        if sql_query:
            section_title("Generated SQL")
            sql_block(sql_query)

        result_rows = turn.get("sql_result") or []
        if not result_rows and turn.get("cache_hit"):
            result_rows = turn["cache_hit"].get("execution_result") or []

        if result_rows:
            section_title("Result table")
            if isinstance(result_rows, list):
                render_result_table(result_rows)
            else:
                render_json_preview(result_rows, label="Result payload")

        if turn.get("cache_hit"):
            with st.expander("Cached answer details"):
                st.write(f"Cache decision: {turn.get('cache_decision', 'MISS')}")
                st.write(f"Similarity: {turn.get('similarity', 0.0):.2f}")
                render_json_preview(turn["cache_hit"], label="Cached payload")


def render_chat(graph):
    """Main chat rendering function. Called from app.py."""
    session_id = st.session_state.get("current_session_id")
    if not session_id:
        st.info("Create a new chat to begin.")
        return

    turns = load_turns(session_id)
    if not turns:
        st.markdown(
            """
            <div style="padding:26px 0 18px;max-width:760px">
                <div style="font-size:30px;font-weight:800;color:#0f172a;margin-bottom:10px">
                    Ask IntelliQ about your data
                </div>
                <div style="font-size:15px;line-height:1.7;color:#475569">
                    Start with a business question. IntelliQ will generate the SQL, execute it,
                    and show the reasoning, result rows, and final answer in one place.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for turn in turns:
        _render_turn(turn)

    st.markdown("<div style='height:110px'></div>", unsafe_allow_html=True)

    user_input = st.chat_input("Ask IntelliQ about your data...")
    if user_input:
        _handle_query(user_input, graph)


def _handle_query(query: str, graph):
    """Invoke the agent graph and store the result in session state."""
    session_id = st.session_state.get("current_session_id")
    thread_id = st.session_state.get("current_thread_id") or session_id or "main"
    config = {"configurable": {"thread_id": thread_id}}

    with st.spinner("Thinking..."):
        result = graph.invoke({"user_query": query, **RESET}, config=config)

    turn = {
        "user": query,
        "response": result.get("final_response", "No response."),
        "cache_decision": result.get("cache_decision"),
        "query_type": result.get("query_type"),
        "sql_query": result.get("sql_query") or result.get("cache_hit", {}).get("generated_sql"),
        "sql_result": result.get("sql_result"),
        "similarity": result.get("cache_hit", {}).get("similarity", 0.0) if result.get("cache_hit") else 0.0,
        "cache_hit": result.get("cache_hit"),
    }

    if session_id:
        save_turn(session_id, turn)

    st.rerun()
