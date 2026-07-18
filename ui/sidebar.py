"""
ui/sidebar.py
Renders the left sidebar:
  - Chat session loader
  - Database and cache summary
  - Session controls
"""

import pandas as pd
import streamlit as st

from core.cache import cache_stats, get_all_cache_entries
from core.database import db_stats
from core.rate_limiter import tracker
from ui.components import section_title
from ui.history_store import create_session, delete_session, list_sessions, rename_session


def _set_current_session(session: dict):
    st.session_state["current_session_id"] = session["session_id"]
    st.session_state["current_thread_id"] = session["thread_id"]


def _new_chat():
    session = create_session()
    _set_current_session(session)


def render_sidebar(sessions=None, db_summary=None, cache_summary=None):
    if sessions is None:
        sessions = list_sessions()
    if db_summary is None:
        db_summary = db_stats()
    if cache_summary is None:
        cache_summary = cache_stats()

    with st.sidebar:
        section_title("Chats")
        st.button("+ New chat", use_container_width=True, on_click=_new_chat)

        if not sessions:
            st.caption("No saved chats yet. Start a conversation to create the first one.")
        else:
            session_map = {s["session_id"]: s for s in sessions}

            def _label(session_id: str) -> str:
                session = session_map[session_id]
                return f"{session['title']}  ·  {int(session['turn_count'])} turns"

            current_id = st.session_state.get("current_session_id")
            if current_id not in session_map:
                current_id = sessions[0]["session_id"]
                _set_current_session(session_map[current_id])

            selected = st.selectbox(
                "Saved conversations",
                options=[s["session_id"] for s in sessions],
                index=[s["session_id"] for s in sessions].index(current_id),
                format_func=_label,
                label_visibility="collapsed",
            )
            if selected != current_id:
                _set_current_session(session_map[selected])
                st.rerun()

            active = session_map[st.session_state["current_session_id"]]
            cols = st.columns(2)
            cols[0].metric("Turns", int(active["turn_count"]))
            cols[1].metric("Updated", pd.to_datetime(active["updated_at"], unit="s").strftime("%b %d"))

            with st.expander("Chat actions"):
                new_title = st.text_input("Rename current chat", value=active["title"], key="rename_chat_input")
                if st.button("Save title", use_container_width=True):
                    rename_session(active["session_id"], new_title.strip() or active["title"])
                    st.rerun()
                if len(sessions) > 1 and st.button("Delete current chat", use_container_width=True):
                    delete_session(active["session_id"])
                    remaining = list_sessions()
                    if remaining:
                        _set_current_session(remaining[0])
                    else:
                        _new_chat()
                    st.rerun()

        st.divider()

        section_title("Database")
        st.metric("Customers", db_summary["customers"])
        st.metric("Products", db_summary["products"])
        st.metric("Sales rows", db_summary["sales"])

        st.divider()

        section_title("Cache")
        col1, col2 = st.columns(2)
        col1.metric("Entries", cache_summary["entries"])
        col2.metric("Hits", cache_summary["total_hits"])

        st.divider()

        section_title("Activity")
        calls = tracker.get_calls()
        if calls:
            for call in reversed(calls[-8:]):
                st.markdown(
                    f"<div style='font-size:11px;padding:4px 0;border-bottom:1px solid #dde5f1'>"
                    f"<b>{call['node']}</b>"
                    f"<span style='float:right;color:#64748b'>{call['latency_ms']}ms</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No backend activity yet.")

        st.divider()

        section_title("Cache browser")
        entries = get_all_cache_entries()
        if entries:
            for entry in entries[:6]:
                st.markdown(
                    f"<div style='border:1px solid #dbe5f0;border-radius:12px;padding:8px 10px;margin-bottom:8px;background:white'>"
                    f"<div style='font-size:12px;color:#0f172a;margin-bottom:2px'>{entry['user_query'][:56]}{'...' if len(entry['user_query']) > 56 else ''}</div>"
                    f"<div style='font-size:11px;color:#64748b'>{entry['query_type']} · {entry['access_count']} hits · {entry['exec_ms']}ms</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No cache entries yet.")
