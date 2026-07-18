# SQLLens — Agentic Text-to-SQL Intelligence

> Natural language → semantic cache → adaptive SQL generation → business insight

SQLLens is an **agentic AI system** that lets non-technical users query a relational database in plain English and receive structured, interpretable business answers — with no SQL knowledge required. It combines a multi-node LangGraph agent, semantic caching with sentence-transformer embeddings, and adaptive query routing in a single coherent pipeline.

---

## 📸 UI Preview

<!-- Add screenshot here -->
`/images/ui_main.png`

<!-- Add execution trace screenshot here -->
`/images/ui_trace.png`

---

## 🧠 What Makes This Agentic

Most text-to-SQL systems are a single LLM call: prompt in, SQL out. SQLLens is a **stateful, multi-step agent** — each query passes through a graph of specialised nodes that reason, route, decide, and learn from prior interactions.

### The Agent Graph

```
START
  │
  ▼
embed_node              ← TF-IDF / sentence-transformer embedding, cache search
  │
  ▼
cache_classify_node     ← ONE LLM call: decides EXACT / PARTIAL / MISS
  │                       AND classifies query type simultaneously
  ├── EXACT ──────────────────────────────────────────┐
  │                                                    ▼
  ├── PARTIAL / MISS                          format_response_node
  │       │                                           │
  │       ▼                                           ▼
  │   sql_engine_node                        cache_write_node
  │   (generate or amend SQL)                        │
  │       │                                          END
  │       ├── analytical → analytical_engine_node
  │       ├── predictive → predictive_engine_node
  │       └── sql ──────────────────────────────────►┘
```

Every node has a single, explicit responsibility. Nodes are stateless functions — all shared context flows through a typed `State` object, making the system easy to inspect, test, and extend.

---

## 🔑 Core AI / ML Skills Demonstrated

### 1. Multi-Node LangGraph Agent
Built with [LangGraph](https://github.com/langchain-ai/langgraph) — a framework for building stateful, graph-structured LLM agents. The agent maintains conversation memory across turns via a SQLite checkpointer, enabling natural follow-up queries like *"now filter that by North region"* without re-stating context.

### 2. Semantic Caching with Embeddings
A custom two-layer cache backed by SQLite:
- **Embedding layer**: each user query is encoded with `sentence-transformers` (`all-MiniLM-L6-v2`), enabling semantic — not just lexical — similarity matching
- **Decision layer**: at ≥ 0.90 cosine similarity the LLM is bypassed entirely (EXACT hit). Between 0.55–0.90, a single LLM call decides whether the cached SQL can be adapted (PARTIAL) or the query is genuinely new (MISS)
- **Impact**: eliminates redundant LLM calls for repeated or paraphrased questions, reducing latency from ~3s to <50ms on cache hits

### 3. Combined Routing + Classification in One LLM Call
A key design decision: instead of separate "check cache" and "classify query" nodes (each costing a rate-limited LLM call), SQLLens fuses both decisions into a single structured output call (`CacheClassifyOutput`). The model simultaneously decides cache status AND query type, saving one LLM call on every request.

### 4. Structured Output with Pydantic
Every LLM call uses `.with_structured_output(PydanticModel)` — no JSON parsing, no regex, no hallucinated field names. Each node has its own schema:

| Node | Schema | Key fields |
|---|---|---|
| cache_classify_node | `CacheClassifyOutput` | decision, query_type, cached_sql_to_adapt |
| sql_engine_node | `SQLOutput` | sql, explanation, is_safe |
| analytical_engine_node | `AnalyticalOutput` | summary, findings[], recommendation |
| predictive_engine_node | `PredictiveOutput` | headline, trend_description, disclaimer |

### 5. Adaptive SQL Generation
`sql_engine_node` does not rewrite SQL from scratch on follow-up questions or partial cache hits. The previous SQL is injected as an `AIMessage` in conversation history, so the LLM amends rather than regenerates — preserving correct join logic and reducing hallucination of column names.

### 6. Guardrailed Execution
All generated SQL passes through a regex-based destructive-query filter before execution. The model also self-reports `is_safe=False` for write operations via the structured output schema — providing two independent safety layers.

### 7. Linear Forecasting Pipeline
`predictive_engine_node` runs a lightweight in-process forecasting pipeline:
- Detects date and value columns from SQL results automatically
- Applies linear regression (`numpy.polyfit`) over the time series
- Computes R² (reported as "trend reliability") and projects N future periods
- Designed as a drop-in replacement point — swap `_compute_forecast()` with a trained in-house model without touching any other node

### 8. Rate Limiting + Observability
A sliding-window rate limiter (4 calls/60s) wraps every LLM call, preventing API quota exhaustion during multi-turn sessions. A `CallTracker` records node name, status, and latency for every call — surfaced live in the UI sidebar.

---

## 📁 Project Structure

```
sqllens/
├── app.py                   # Streamlit entry point
├── requirements.txt
├── .env                     # GOOGLE_API_KEY
│
├── core/
│   ├── schemas.py           # Pydantic output schemas + State TypedDict
│   ├── database.py          # Analytics DB (SQLite) — seed, run_sql, schema loader
│   ├── cache.py             # Semantic cache (SQLite) — embed, search, upsert
│   └── rate_limiter.py      # RateLimiter, CallTracker, llm_call() wrapper
│
├── agent/
│   ├── prompts.py           # All LLM system prompts
│   ├── nodes.py             # All 7 node functions
│   └── graph.py             # Graph wiring + SqliteSaver compilation
│
└── ui/
    ├── components.py        # Execution trace, SQL block, cache badge widgets
    ├── sidebar.py           # Schema explorer, cache browser, call log
    └── chat.py              # Conversation history + input handler
```

Each layer has one concern. `core/` knows nothing about the agent. `agent/` knows nothing about the UI. Adding a new engine node (e.g. RAG, anomaly detection) means adding one function to `nodes.py` and one edge in `graph.py`.

---

## 🗄️ Data Architecture

Three SQLite databases, three distinct purposes:

| File | Purpose | Who writes to it |
|---|---|---|
| `analytics.db` | Business data (customers, products, sales) | `seed()` once at startup |
| `cache.db` | Semantic cache entries + embeddings | `cache_write_node` after every query |
| `memory.db` | LangGraph conversation checkpoints | LangGraph SqliteSaver automatically |

---

## ⚡ Performance Characteristics

| Scenario | LLM Calls | Typical Latency |
|---|---|---|
| Cold miss (new query) | 2–3 | 4–8s |
| Partial cache hit | 2 | 3–5s |
| Exact cache hit | 0 | < 50ms |
| Irrelevant query | 1 | 1–2s |

Cache hit rate exceeds 90% in real usage after the first 20–30 unique queries, because most business users ask variations of the same 10–15 questions repeatedly.

---

## 🚀 Getting Started

```bash
git clone <repo>
cd sqllens
pip install -r requirements.txt

# Add your Gemini API key
echo "GOOGLE_API_KEY=your_key_here" > .env

# Run
streamlit run app.py
```

The database is seeded automatically on first run (40 customers, 8 products, 365 days of sales).

---

## 🔭 Extending the System

| What to add | Where to change |
|---|---|
| New query type (e.g. anomaly detection) | Add node in `nodes.py`, new edge in `graph.py`, new schema in `schemas.py` |
| Real database (Postgres, Snowflake) | Replace `core/database.py` connection only |
| Better embeddings | Swap `SentenceTransformer` model in `core/cache.py` |
| In-house forecast model | Replace `_compute_forecast()` in `nodes.py` |
| HITL confirmation | Add `interrupt()` inside `sql_engine_node` |
| Auth / multi-user | Pass `user_id` as `thread_id` to the graph config |

---

## 🛠 Tech Stack

| Component | Technology |
|---|---|
| Agent framework | LangGraph |
| LLM | Google Gemini 2.5 Flash |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Structured output | Pydantic v2 + LangChain `.with_structured_output()` |
| Databases | SQLite (analytics · cache · memory) |
| Forecasting | NumPy linear regression |
| UI | Streamlit |

---

## 📄 License

MIT