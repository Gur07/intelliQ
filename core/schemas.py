"""
core/schemas.py
All Pydantic output schemas, the LangGraph State TypedDict, and RESET dict.
Nothing else lives here — import from this file everywhere.
"""

from typing import Optional, List, Dict, Annotated
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ── LLM output schemas ────────────────────────────────────────────────────────

class CacheClassifyOutput(BaseModel):
    """Single LLM call that handles cache routing + query classification together."""
    decision: str = Field(
        description=(
            "Cache routing decision. One of:\n"
            "  EXACT   — cached SQL/response answers this question unchanged\n"
            "  PARTIAL — cached SQL is close but needs adaptation\n"
            "  MISS    — no useful cache match; treat as a fresh query"
        )
    )
    query_type: str = Field(
        description=(
            "Query classification. One of: sql | analytical | predictive | irrelevant | error\n"
            "  sql         — direct data lookup, answer is a table or number\n"
            "  analytical  — needs data AND interpretation/comparison/explanation\n"
            "  predictive  — asks about future values, trends, or forecasts\n"
            "  irrelevant  — unrelated to the database or analytics\n"
            "  error       — empty or completely garbled input\n"
            "For EXACT hits: set to the cached entry's query_type.\n"
            "For PARTIAL/MISS: set based on the new question."
        )
    )
    reasoning: str = Field(
        description="Brief reasoning for the decision and classification."
    )
    cached_sql_to_adapt: Optional[str] = Field(
        default=None,
        description=(
            "Only for PARTIAL: copy the cached SQL here so sql_engine can adapt it. "
            "Leave null for EXACT and MISS."
        )
    )


class SQLOutput(BaseModel):
    sql: str = Field(description="A valid SQLite SELECT query answering the user question")
    explanation: str = Field(description="Plain English: what this query does, one sentence, no jargon")
    is_safe: bool = Field(description="True if read-only SELECT. False if it modifies data.")


class AnalyticalOutput(BaseModel):
    summary: str = Field(description="1-2 sentence headline takeaway for a non-technical reader")
    findings: List[str] = Field(description="3-5 bullet findings each citing a specific number from the data")
    recommendation: str = Field(description="One actionable business recommendation")


class PredictiveOutput(BaseModel):
    headline: str = Field(description="One sentence forecast in plain English")
    trend_description: str = Field(description="2-3 sentences on trend direction and reliability")
    recommendation: str = Field(description="One sentence business recommendation")
    disclaimer: str = Field(description="One sentence: this is a projection, not a guarantee")


# ── Graph state ───────────────────────────────────────────────────────────────

class State(TypedDict):
    # Conversation memory — persisted across turns by SqliteSaver checkpointer
    messages:        Annotated[List[BaseMessage], add_messages]
    # Per-turn input
    user_query:      str
    # Cache layer
    cache_decision:  Optional[str]        # EXACT | PARTIAL | MISS
    cache_hit:       Optional[Dict]       # best cache row returned by search_cache()
    cache_embedding: Optional[List[float]]  # stored as list (JSON-serialisable)
    cache_t0:        Optional[float]      # wall-clock start for execution_time tracking
    # Classification
    query_type:      Optional[str]        # sql | analytical | predictive | irrelevant | error
    # SQL / engine results
    sql_query:       Optional[str]        # NOT reset between turns — used for follow-up context
    sql_result:      Optional[List[Dict]]
    sql_explanation: Optional[str]
    analysis:        Optional[str]
    prediction:      Optional[str]
    # Final output
    final_response:  Optional[str]
    error:           Optional[str]


# Reset dict applied at the start of every new turn.
# sql_query is intentionally excluded — it carries forward for follow-up amends.
RESET: Dict = dict(
    cache_decision=None, cache_hit=None, cache_embedding=None, cache_t0=None,
    query_type=None, sql_result=None, sql_explanation=None,
    analysis=None, prediction=None, final_response=None, error=None,
)
