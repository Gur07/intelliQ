"""
app.py
Streamlit entry point for IntelliQ.

Run with:
    streamlit run app.py
"""

from dotenv import load_dotenv
import streamlit as st

load_dotenv()

from agent.graph import build_graph
from core.cache import cache_stats
from core.database import db_stats, seed
from core.rate_limiter import tracker
from ui.history_store import create_session, list_sessions
from ui.chat import render_chat
from ui.sidebar import render_sidebar


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IntelliQ",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(30,136,229,0.10), transparent 28%),
                radial-gradient(circle at top right, rgba(14,165,233,0.08), transparent 24%),
                #f7f9fc;
            color: #0f172a;
        }

        #MainMenu, footer { visibility: hidden; }

        header[data-testid="stHeader"] {
            background: transparent;
            box-shadow: none;
        }

        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fbff 0%, #eef4fb 100%);
            border-right: 1px solid #dbe5f0;
        }

        .top-shell {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 14px 2px 18px;
            margin-bottom: 8px;
            border-bottom: 1px solid #dbe5f0;
        }

        .brand-row {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-mark {
            width: 38px;
            height: 38px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #1e88e5, #0ea5e9);
            color: white;
            font-size: 18px;
            box-shadow: 0 10px 24px rgba(30,136,229,0.25);
        }

        .brand-title {
            font-size: 18px;
            font-weight: 800;
            color: #0f172a;
            line-height: 1.1;
        }

        .brand-subtitle {
            font-size: 11px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            margin-top: 2px;
        }

        .chip-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }

        .metric-chip {
            min-width: 96px;
            padding: 10px 14px;
            border-radius: 16px;
            border: 1px solid #d7e3f2;
            background: rgba(255,255,255,0.84);
            box-shadow: 0 8px 24px rgba(15,23,42,0.05);
        }

        .metric-label {
            font-size: 10px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.10em;
            margin-bottom: 4px;
        }

        .metric-value {
            font-size: 18px;
            font-weight: 800;
            color: #1e88e5;
        }

        .section-title {
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: #475569;
            margin: 8px 0 10px;
        }

        .stButton > button {
            border-radius: 12px;
            border: 1px solid #c8d7ea;
            background: white;
            color: #0f172a;
            font-weight: 600;
        }

        .stButton > button:hover {
            border-color: #1e88e5;
            color: #1e88e5;
            background: #eff6ff;
        }

        .stChatInput textarea {
            border-radius: 18px !important;
            border: 1px solid #cbd8ea !important;
            background: white !important;
            color: #0f172a !important;
            box-shadow: 0 10px 28px rgba(15,23,42,0.08) !important;
        }

        [data-testid="stMetric"] {
            border-radius: 16px;
            background: rgba(255,255,255,0.85);
            border: 1px solid #dde7f3;
            padding: 10px 12px;
        }

        [data-testid="stMetricValue"] {
            color: #0f172a !important;
            font-weight: 800 !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── One-time startup ──────────────────────────────────────────────────────────
@st.cache_resource
def startup():
    seed()
    return build_graph()


graph = startup()

if "current_session_id" not in st.session_state:
    sessions = list_sessions()
    if sessions:
        st.session_state["current_session_id"] = sessions[0]["session_id"]
        st.session_state["current_thread_id"] = sessions[0]["thread_id"]
    else:
        session = create_session()
        st.session_state["current_session_id"] = session["session_id"]
        st.session_state["current_thread_id"] = session["thread_id"]


sessions = list_sessions()
summary = tracker.summary()
history_queries = sum(int(s.get("turn_count") or 0) for s in sessions)
cache_summary = cache_stats()

st.markdown(
    f"""
    <div class="top-shell">
        <div class="brand-row">
            <div class="brand-mark">🔎</div>
            <div>
                <div class="brand-title">IntelliQ</div>
                <div class="brand-subtitle">SQL Intelligence workspace</div>
            </div>
        </div>
        <div class="chip-row">
            <div class="metric-chip">
                <div class="metric-label">Hit rate</div>
                <div class="metric-value">{int(summary["cached"] / summary["total"] * 100) if summary["total"] else 0}%</div>
            </div>
            <div class="metric-chip">
                <div class="metric-label">Latency</div>
                <div class="metric-value">{summary["avg_ms"]}ms</div>
            </div>
            <div class="metric-chip">
                <div class="metric-label">Queries</div>
                <div class="metric-value">{history_queries}</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

render_sidebar(sessions=sessions, db_summary=db_stats(), cache_summary=cache_summary)
render_chat(graph)
