"""
agent/nodes.py
All 7 LangGraph node functions.
Logic is identical to the working notebook — only imports changed.
"""

import json
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.cache import (
    embed_query, search_cache, upsert_cache, cache_stats,
    CACHE_SIMILARITY_THRESHOLD,
)
from core.database import is_safe, run_sql
from core.rate_limiter import llm_call, tracker
from core.schemas import (
    AnalyticalOutput, CacheClassifyOutput, PredictiveOutput, SQLOutput, State,
)


# Populated by graph.py before the graph is compiled
_chains: Dict = {}
_prompts: Dict = {}

FORCE_MISS_THRESHOLD = 0.55


def set_chains(chains: Dict, prompts: Dict):
    """Called once from graph.py after the LLM is initialised."""
    global _chains, _prompts
    _chains  = chains
    _prompts = prompts


# ── Node 1: embed_node ────────────────────────────────────────────────────────

def embed_node(state: State) -> dict:
    """Embed the query and search the cache. No LLM call."""
    t0        = time.time()
    embedding = embed_query(state["user_query"])
    hit       = search_cache(embedding)
    sim       = hit["similarity"] if hit else 0.0

    tracker.record("embed_node", "ok", int((time.time() - t0) * 1000), f"sim={sim:.3f}")
    return {
        "cache_hit":       hit,
        "cache_embedding": embedding.tolist(),
        "cache_t0":        time.time(),
    }


# ── Node 2: cache_classify_node ───────────────────────────────────────────────

def cache_classify_node(state: State) -> dict:
    """
    Single LLM call that decides EXACT / PARTIAL / MISS
    and classifies the query type — all at once.
    Below FORCE_MISS_THRESHOLD the LLM still runs (for classification)
    but is told there is no useful cache match.
    """
    hit = state.get("cache_hit")
    sim = hit["similarity"] if hit else 0.0

    if sim < FORCE_MISS_THRESHOLD or hit is None:
        content = (
            f"NEW question: {state['user_query']}\n\n"
            f"Cached entry: NONE (cache empty or similarity too low: {sim:.3f})\n\n"
            "Set decision=MISS and classify the new question."
        )
    else:
        content = (
            f"NEW question: {state['user_query']}\n\n"
            f"Similarity score: {sim:.3f}\n\n"
            f"Closest cached question: {hit['user_query']}\n"
            f"Cached SQL:\n{hit['generated_sql']}\n"
            f"Cached query_type: {hit['query_type']}\n"
            f"Cached response (summary):\n{str(hit['final_response'])[:300]}"
        )

    result: CacheClassifyOutput = llm_call(
        "cache_classify_node",
        _chains["cache_classify"],
        [SystemMessage(content=_prompts["cache_classify"]),
         HumanMessage(content=content)],
    )

    updates: Dict = {
        "cache_decision": result.decision,
        "query_type":     result.query_type,
        "messages":       [HumanMessage(content=state["user_query"])],
    }
    # For PARTIAL: pass cached SQL so sql_engine amends rather than rewrites
    if result.decision == "PARTIAL" and result.cached_sql_to_adapt:
        updates["sql_query"] = result.cached_sql_to_adapt

    return updates


# ── Node 3: sql_engine_node ───────────────────────────────────────────────────

def sql_engine_node(state: State) -> dict:
    """Generate (or amend) SQL, guardrail it, execute it."""
    history = list(state["messages"][-6:])
    if state.get("sql_query"):
        history.append(AIMessage(
            content=(
                "Previous SQL (amend for follow-ups / partial cache hits):\n"
                f"```sql\n{state['sql_query']}\n```"
            )
        ))

    result: SQLOutput = llm_call(
        "sql_engine",
        _chains["sql"],
        [SystemMessage(content=_prompts["sql"])]
        + history
        + [HumanMessage(content=state["user_query"])],
    )

    if not result.is_safe or not is_safe(result.sql):
        tracker.record("sql_engine", "blocked", 0, "destructive SQL blocked")
        return {"error": f"Blocked: this query modifies data.\nSQL: {result.sql}"}

    try:
        rows = run_sql(result.sql)
        return {
            "sql_query":       result.sql,
            "sql_explanation": result.explanation,
            "sql_result":      rows,
            "error":           None,
            "messages":        [AIMessage(content=f"SQL: {result.explanation}")],
        }
    except Exception as e:
        return {"error": str(e)}


# ── Node 4: analytical_engine_node ───────────────────────────────────────────

def analytical_engine_node(state: State) -> dict:
    """Interpret the SQL result and produce a business narrative."""
    if state.get("error") or not state.get("sql_result"):
        return {"analysis": None}

    rows   = state["sql_result"]
    result: AnalyticalOutput = llm_call(
        "analytical_engine",
        _chains["analytical"],
        [SystemMessage(content=_prompts["analytical"]),
         HumanMessage(content=(
             f"User question: {state['user_query']}\n\n"
             f"SQL: {state['sql_query']}\n\n"
             f"Result ({len(rows)} rows, first 20):\n{json.dumps(rows[:20], default=str)}"
         ))],
    )
    findings_text = "\n".join(f"• {f}" for f in result.findings)
    return {"analysis": (
        f"**Summary:** {result.summary}\n\n"
        f"**Key Findings:**\n{findings_text}\n\n"
        f"**Recommendation:** {result.recommendation}"
    )}


# ── Node 5: predictive_engine_node ───────────────────────────────────────────

def _compute_forecast(rows: List[Dict], n: int = 7) -> str:
    df        = pd.DataFrame(rows)
    date_col  = next((c for c in df.columns if "date" in c.lower() or "month" in c.lower()), None)
    value_col = next((c for c in df.columns if df[c].dtype.kind in "if"), None)
    if not date_col or not value_col or len(df) < 4:
        return "Not enough time-series data (need date + numeric column, min 4 rows)."
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    y  = df[value_col].astype(float).values
    x  = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    y_hat = slope * x + intercept
    r2    = round(1 - np.sum((y - y_hat) ** 2) / np.sum((y - y.mean()) ** 2), 3)
    fcast = [round(slope * (len(y) + i) + intercept, 2) for i in range(n)]
    return (
        f"Metric: {value_col} | Points: {len(y)} | "
        f"Slope: {slope:+.2f}/period | R2: {r2} | Forecast: {fcast}"
    )


def predictive_engine_node(state: State) -> dict:
    """Run linear forecast and produce a plain-English narrative."""
    if state.get("error") or not state.get("sql_result"):
        return {"prediction": None}

    result: PredictiveOutput = llm_call(
        "predictive_engine",
        _chains["predictive"],
        [SystemMessage(content=_prompts["predictive"]),
         HumanMessage(content=(
             f"User question: {state['user_query']}\n\n"
             f"Historical SQL: {state['sql_query']}\n\n"
             f"Forecast: {_compute_forecast(state['sql_result'])}"
         ))],
    )
    return {"prediction": (
        f"**Forecast:** {result.headline}\n\n"
        f"**Trend:** {result.trend_description}\n\n"
        f"**Recommendation:** {result.recommendation}\n\n"
        f"_{result.disclaimer}_"
    )}


# ── Node 6: format_response_node ─────────────────────────────────────────────

def format_response_node(state: State) -> dict:
    """
    Assemble the final response string.
    EXACT cache hit → serve stored response directly (no engine nodes ran).
    All other paths → build from analysis / prediction / sql_result / error.
    """
    qt       = state.get("query_type", "error")
    decision = state.get("cache_decision", "MISS")

    if decision == "EXACT" and state.get("cache_hit"):
        final = state["cache_hit"]["final_response"]
        tracker.record("format_response", "cache", 0, "EXACT cache hit")
        return {"final_response": final, "messages": [AIMessage(content=final)]}

    if state.get("error"):
        final = f"Something went wrong:\n\n{state['error']}"
    elif qt == "irrelevant":
        final = "I can only help with questions about the sales database — customers, products, revenue, and forecasts."
    elif qt == "error":
        final = "I couldn't understand that. Could you rephrase?"
    elif state.get("analysis"):
        final = state["analysis"]
    elif state.get("prediction"):
        final = state["prediction"]
    elif state.get("sql_result") is not None:
        rows    = state["sql_result"]
        n       = len(rows)
        preview = json.dumps(rows[:10], default=str, indent=2)
        expl    = f"\n_{state['sql_explanation']}_\n" if state.get("sql_explanation") else ""
        more    = f"\n...and {n - 10} more rows." if n > 10 else ""
        final   = f"Found **{n}** result(s).{expl}\n```json\n{preview}\n```{more}"
    else:
        final = "I wasn't able to produce an answer. Please try rephrasing."

    return {"final_response": final, "messages": [AIMessage(content=final)]}


# ── Node 7: cache_write_node ──────────────────────────────────────────────────

def cache_write_node(state: State) -> dict:
    """
    Always runs last (before END).
    EXACT  → increment hit count only.
    MISS / PARTIAL → full upsert with new embedding + SQL + result.
    Irrelevant / error → skip.
    """
    qt       = state.get("query_type", "error")
    decision = state.get("cache_decision", "MISS")
    final    = state.get("final_response", "")

    if qt in ("irrelevant", "error") or state.get("error"):
        return {}

    execution_time = time.time() - (state.get("cache_t0") or time.time())
    embedding      = np.array(state["cache_embedding"]) if state.get("cache_embedding") else None

    if decision == "EXACT" and state.get("cache_hit"):
        upsert_cache(
            user_query=state["user_query"], embedding=embedding,
            sql=state["cache_hit"]["generated_sql"],
            result=state["cache_hit"]["execution_result"],
            metadata=state["cache_hit"]["metadata"],
            query_type=qt, final_response=final,
            execution_time=execution_time,
            reused_cache_id=state["cache_hit"]["cache_id"],
        )
    else:
        metadata = {
            "tables":     list({t for t in ["customers", "products", "sales"]
                                if state.get("sql_query") and t in (state["sql_query"] or "")}),
            "query_type": qt,
            "decision":   decision,
        }
        upsert_cache(
            user_query=state["user_query"], embedding=embedding,
            sql=state.get("sql_query"), result=state.get("sql_result"),
            metadata=metadata, query_type=qt, final_response=final,
            execution_time=execution_time,
        )

    return {}
