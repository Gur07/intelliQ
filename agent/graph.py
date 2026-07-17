"""
agent/graph.py
Wires all nodes into the LangGraph StateGraph and compiles it.
Call build_graph() once at app startup — it returns the compiled graph.
"""

import os
import sqlite3

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    analytical_engine_node,
    cache_classify_node,
    cache_write_node,
    embed_node,
    format_response_node,
    predictive_engine_node,
    set_chains,
    sql_engine_node,
)
from agent.prompts import build_prompts
from core.database import load_schema
from core.schemas import (
    AnalyticalOutput,
    CacheClassifyOutput,
    PredictiveOutput,
    SQLOutput,
    State,
)

MEMORY_DB_PATH = "memory.db"


def route_after_cache_classify(state: State) -> str:
    decision = state.get("cache_decision", "MISS")
    qt       = state.get("query_type", "error")
    if decision == "EXACT":
        return "format_response"        # serve cache, skip all engines
    if qt in ("irrelevant", "error"):
        return "format_response"        # no SQL needed
    return "sql_engine"                 # MISS or PARTIAL → generate / adapt SQL


def route_after_sql(state: State) -> str:
    if state.get("error"):
        return "format_response"
    qt = state.get("query_type")
    if qt == "analytical":
        return "analytical_engine"
    if qt == "predictive":
        return "predictive_engine"
    return "format_response"


def build_graph():
    """
    Initialise LLM, bind structured-output chains, build and compile the graph.
    Returns the compiled graph ready for graph.invoke().
    """
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, api_key=api_key)

    schema  = load_schema()
    prompts = build_prompts(schema)

    chains = {
        "cache_classify": llm.with_structured_output(CacheClassifyOutput),
        "sql":            llm.with_structured_output(SQLOutput),
        "analytical":     llm.with_structured_output(AnalyticalOutput),
        "predictive":     llm.with_structured_output(PredictiveOutput),
    }

    # Inject chains + prompts into nodes module
    set_chains(chains, prompts)

    # Build graph
    g = StateGraph(State)

    g.add_node("embed_node",          embed_node)
    g.add_node("cache_classify_node", cache_classify_node)
    g.add_node("sql_engine",          sql_engine_node)
    g.add_node("analytical_engine",   analytical_engine_node)
    g.add_node("predictive_engine",   predictive_engine_node)
    g.add_node("format_response",     format_response_node)
    g.add_node("cache_write_node",    cache_write_node)

    g.add_edge(START, "embed_node")
    g.add_edge("embed_node", "cache_classify_node")

    g.add_conditional_edges(
        "cache_classify_node", route_after_cache_classify,
        {"format_response": "format_response", "sql_engine": "sql_engine"},
    )
    g.add_conditional_edges(
        "sql_engine", route_after_sql,
        {
            "analytical_engine": "analytical_engine",
            "predictive_engine": "predictive_engine",
            "format_response":   "format_response",
        },
    )

    g.add_edge("analytical_engine", "format_response")
    g.add_edge("predictive_engine", "format_response")
    g.add_edge("format_response",   "cache_write_node")
    g.add_edge("cache_write_node",  END)

    # SQLite checkpointer — conversation memory only
    conn   = sqlite3.connect(MEMORY_DB_PATH, check_same_thread=False)
    memory = SqliteSaver(conn)

    return g.compile(checkpointer=memory)
