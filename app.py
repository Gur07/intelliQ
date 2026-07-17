"""
app.py
Streamlit entry point for SQLLens.

Run with:
    streamlit run app.py
"""

import os

import streamlit as st
from dotenv import load_dotenv

# Load .env before anything that needs GOOGLE_API_KEY
load_dotenv()

from agent.graph import build_graph
from core.database import seed
from ui.chat import render_chat
from ui.sidebar import render_sidebar


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SQLLens — SQL Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        /* Dark background */
        .stApp { background-color: #0a0f1e; }

        /* Hide Streamlit chrome */
        #MainMenu, header, footer { visibility: hidden; }

        /* Top bar */
        .top-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 0 18px;
            border-bottom: 1px solid #1e293b;
            margin-bottom: 16px;
        }

        /* Sidebar styling */
        section[data-testid="stSidebar"] {
            background: #0d1424;
            border-right: 1px solid #1e293b;
        }

        /* Input box */
        .stChatInput textarea {
            background: #1e293b !important;
            border: 1px solid #334155 !important;
            color: #e2e8f0 !important;
            border-radius: 12px !important;
        }

        /* Buttons */
        .stButton > button {
            background: #1e293b;
            color: #e2e8f0;
            border: 1px solid #334155;
            border-radius: 8px;
        }
        .stButton > button:hover {
            background: #334155;
            border-color: #1E88E5;
        }

        /* Metrics */
        [data-testid="stMetricValue"] {
            font-size: 18px !important;
            font-weight: 700 !important;
            color: #1E88E5 !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── One-time startup ──────────────────────────────────────────────────────────
@st.cache_resource
def startup():
    """Seed DB and build graph exactly once per Streamlit session."""
    seed()
    return build_graph()


graph = startup()


# ── Top bar ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="top-bar">
        <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:20px">🔍</span>
            <span style="font-weight:700;font-size:16px;color:#e2e8f0">SQLLens</span>
            <span style="
                background:#22c55e18;border:1px solid #22c55e44;
                color:#22c55e;font-size:10px;font-weight:600;
                border-radius:12px;padding:2px 8px;letter-spacing:.5px">
                ● OPTIMAL
            </span>
        </div>
        <div style="font-size:12px;color:#64748b">Gemini 2.5 Flash · SQLite</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Layout ────────────────────────────────────────────────────────────────────
render_sidebar()
render_chat(graph)
