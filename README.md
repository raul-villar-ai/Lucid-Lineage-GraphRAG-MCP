Status: Personal Exploratory PoC — feature-complete for the current phase

# Lucid Lineage GraphRAG MCP

**Lucid Lineage** is a personal proof-of-concept (PoC) and exploratory project demonstrating the practical application of agentic AI and Knowledge GraphRAG (Retrieval-Augmented Generation) technology. It explores how an autonomous orchestration framework can map mock infrastructure dependencies and evaluate data boundary anomalies within a simulated sandbox environment.

### 💡 Personal Project Notice

Lucid Lineage is an independent, open-source personal research project built entirely in my own time using public libraries. The code, architectural design, and synthetic datasets contained in this repository are created solely in an individual capacity for learning and brand-building purposes. They do not reflect the views, strategies, or technologies of any current or past employers, nor was any corporate time, hardware, or intellectual property used in the making of this project.

All organisations, assets, compliance boundaries, and "violations" in this project are fictional test fixtures operating on synthetic data. Released under the **MIT License** — see [`LICENSE`](LICENSE). © 2026 Raul Villar Robledo.

## Project Summary
This project evaluates how a **Neo4j knowledge graph** can be paired with LLM-driven reasoning to trace simulated data flows and analyze mock compliance constraints (such as illustrative GDPR, SOX, or CCPA frameworks). It leverages a LangChain-orchestrated reasoning agent to traverse an experimental graph database, test deterministic graph-querying tools, and log simulated audit findings back into the database for analysis.

## Codebase Guide

The project serves as an **exploratory GraphRAG architecture pattern**: a LangChain agent (backed by **Google Gemini**) reasons over a mock **Neo4j** knowledge graph, interacts with deterministic graph tools, and logs simulated findings back to the graph environment. At runtime, a presentation entry point calls `run_trace()`, which lets the agent evaluate and select appropriate graph tools; those tools execute parameterized Cypher through a singleton driver against the Neo4j instance.


```
app.py / main.py   →   run_trace()          →   Gemini selects tools
(presentation)         (src/agent.py)            │
                            │                    src/graph_tools.py  →  src/db.py  →  Neo4j Aura
                            │                                                  │
             returns per-submission scope                     src/graph_view.py (read-only)
             (touched assets / locations)  ───────────────►   Knowledge Graph tab highlight
```

A core principle is **single-source-of-truth**: all Cypher business logic lives in `src/graph_tools.py` (shared by the agent *and* the MCP server); all model configuration lives in `src/llm.py` (shared by the UI *and* the CLI).

### Presentation layer
* `app.py` — Streamlit web UI ("Forensic Workspace"). Two tabs: a **🔎 Forensic Workspace** (access-control sidebar for IAM role / clearance boundary, chat rendering, the per-submission security "traffic light", and per-prompt calls to `run_trace()`), and a **🕸️ Knowledge Graph** tab that visualizes the graph and highlights the subgraph the last query touched. Manages session state and records each submission's touched scope for the graph tab to consume.
* `main.py` — CLI "Forensic Terminal": builds the live agent and loops over audit queries → `run_trace()` → prints results (with a Windows UTF-8 console guard).

### Orchestration layer
* `src/agent.py` — The core. Defines the six LangChain `@tool` wrappers, the Neo4j-backed chat memory (`get_graph_memory` / `save_graph_memory`, including primitive-serialization normalization), and `run_trace()` — the main pipeline (bounded history → role/clearance-aware prompt → `create_tool_calling_agent` + `AgentExecutor` with iteration/time caps → normalized, persisted answer). The agent now captures **which assets and compute nodes each submission investigated** (`_extract_query_scope`, via `return_intermediate_steps`); with `return_details=True`, `run_trace()` returns `{answer, touched_assets, touched_locations, full_scan}` so the UI can scope the security light and graph highlight to the current turn. The prompt enforces read-only discipline (only logs a finding when explicitly asked), classification-scoped answers, distinct-asset counts, and findings grounded strictly in retrieved data. Falls back to a mock response when no LLM is supplied.
* `src/llm.py` — LLM factory & **provider toggle**: builds either Google Gemini (`gemini-3.5-flash`) or OpenAI (`gpt-4o-mini`), selected via `LLM_PROVIDER` in `.env` (or the `DEFAULT_PROVIDER` constant). Single source of truth for model config.

### Data access layer
* `src/graph_tools.py` — The unified Cypher query layer; all Neo4j business logic. Six tools: asset-lineage trace, co-location "blast radius", compliance-boundary check, write audit finding, retrieve past findings, and the cross-boundary leak scan. The leak scan excludes the false positive where a single node governed by multiple boundaries would otherwise look like a leak, and counts each incident once — but the two call sites use *different, individually-correct* predicates for this: the tool (`query_restricted_asset_leaks`) applies a **canonical ordering** (`c1.name < c2.name`) so every offending node pair is listed exactly once for drill-down, while the parallel security-light scans in `src/graph_admin.py` use the equivalent **identity guard** (`c1 <> c2`) because they only need a distinct-asset count. Both yield the same set of affected assets; the headline reports **distinct affected assets**. All queries are parameterized (injection-safe).
* `src/db.py` — Thread-safe singleton Neo4j driver (bounded connection pool + acquisition timeout), plus connectivity verification and graceful shutdown.
* `src/graph_admin.py` — Graph administration & health: reseeds the graph from the canonical Cypher, detects drift from the seeded baseline (SHA-256 fingerprint), and computes the security "traffic light". Exposes a whole-graph scan (`security_status`), an **asset-scoped** scan (`security_status_for_assets`) and a location→assets resolver (`assets_on_locations`) so the light can reflect the specific submission; a shared `_classify` helper keeps the RED/AMBER/GREEN logic identical across both scans. The leak component of each scan also uses the `c1 <> c2` guard.

### Presentation — knowledge graph visualization
* `src/graph_view.py` — Renders the enterprise knowledge graph on the dedicated Streamlit tab using **st-link-analysis** (a Cytoscape.js component). The base graph is queried from Neo4j **once and cached** (`@st.cache_data`); each chat submission only recomputes which nodes are highlighted — the touched assets/locations plus their one-hop neighbourhood stay vivid while the rest dims. Because the component is keyed, it reconciles in place on Streamlit's automatic rerun (no iframe reload, no re-query), so the view updates as the conversation progresses without a manual refresh.

### Tool bridging & observability
* `src/mcp_server.py` — FastMCP server exposing the same six tools via the Model Context Protocol, so external MCP clients use identical Cypher and schema.
* `src/telemetry.py` — OpenTelemetry instrumentation; the `trace_tool` decorator records spans, non-secret arguments, latency, and success/failure for `run_trace` and each graph tool.
* `src/__init__.py` — Package docstring / module map.

### Data & persistence
* `data/init_graph.cypher` — Enterprise graph seed script: compliance boundaries, compute nodes, data assets, service accounts, their lineage relationships, and **intentional** compliance violations used as test fixtures.
* `seed_db.py` — Loads and executes `data/init_graph.cypher` to provision or reset the graph.

### Diagnostics
* `check_env.py` — Verifies Neo4j Aura connectivity and authentication from `.env`.
* `check_models.py` — Lists the Gemini models the configured API key can access.

### Testing & validation
* `TESTCASES.md` — The three canonical scenarios (each a primary + follow-up query).
* `eval/run_testcases.py` — Automated harness that runs the scenarios (primary + follow-up on a shared session to exercise memory) and captures responses, tools invoked, timing, and errors.
* `TESTCASES_LOG.md` — Audit log of test-run results (pass/fail status and any trace errors).

### Infrastructure as Code (planned deployment — see `ARCHITECTURE.md`, Milestone C)
* `infra/main.tf` — Terraform: Vertex AI endpoint, a (mock) Neo4j host, and a Cloud Run service for the Streamlit UI (region `europe-west2` for sovereignty).
* `infra/iam.tf` — Terraform: zero-trust IAM — custom agent role, service account, and role bindings.
* `infra/variables.tf` — Terraform input variables (`project_id`, `region`, `streamlit_service_name`).

### Configuration & documentation
* `.env` — Secrets/config: Neo4j credentials, provider toggle, and LLM API key(s) (gitignored). Note: `PROJECT_ID` is **not** read from `.env` — it is a Terraform input variable (`infra/variables.tf`), supplied at `terraform apply` time.
* `requirements.txt` — Python dependencies, aligned to the code's actual direct imports (includes `st-link-analysis` for the graph tab).
* `ARCHITECTURE.md`: Core system architecture, target state, and graph schema.
* `CLEANUP_LOG.md`: Housekeeping audit trail (what was reviewed/removed and why).

### Graph schema (quick reference)
* **Nodes:** `Data_Asset`, `Compute_Node`, `Compliance_Boundary`, `Service_Account`, `Audit_Finding` (plus `Session` / `Message` for chat memory).
* **Edges:** `STORED_ON`, `REPLICATED_TO`, `GOVERNED_BY`, `HAS_ACCESS`, `HAS_AUDIT_RECORD`.

## Known Limitations

Lucid Lineage has two layers with very different reliability characteristics, and the
boundary between them matters when interpreting output:

* **Deterministic query layer** (`src/graph_tools.py`, `src/graph_admin.py`) — parameterized
  Cypher with fixed semantics. Once a query is correct it stays correct and is reproducible
  run-to-run: the cross-boundary leak scan returns the same distinct-asset set every time, and
  `resolve_location()` maps a location phrase to a node name by fixed rules.
* **Agent reasoning layer** (`src/agent.py` + the LLM) — probabilistic. It decides which tools to
  call and how to phrase answers, and it can err *even when the underlying data is correct* — most
  notably by (a) reporting a row count instead of the DISTINCT-asset count, and (b) resolving an
  informal location phrase to the wrong node under conversational context drift.

Concrete example from this project's own testing: asked in-session about "the APAC gateway
location" after two turns about a *different* APAC node, the agent resolved it to
`APAC_Singapore_Analytics` instead of `APAC_Edge_Gateway` (and logged a mis-targeted audit finding
off that); separately it reported "3 Highly_Restricted assets" for what were 2 distinct assets
across 3 boundary-crossing paths. The mitigations for these — a `classification`-aware leak count
returned by the tool itself, and a deterministic `resolve_location` step the agent is instructed
to call before any location lookup — **reduce** these error modes but do **not** eliminate them;
the reasoning layer remains probabilistic. Treat agent output as decision support, and rely on the
deterministic tools / the graph directly for anything authoritative.

## Setup Instructions
Create a `.env` file in the root directory:
```env
NEO4J_URI=neo4j+s://<your-db-id>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your-password>

# LLM provider toggle: "google" (default) or "openai"
LLM_PROVIDER=google
GOOGLE_API_KEY=<your-gemini-api-key>
# Required only when LLM_PROVIDER=openai
OPENAI_API_KEY=<your-openai-api-key>
```

Then install dependencies, seed the graph, and launch:
```bash
pip install -r requirements.txt
python seed_db.py            # provision / reset the Neo4j graph
streamlit run app.py         # web UI   (or:  python main.py  for the CLI)
```

Verify connectivity at any time with `python check_env.py` and `python check_models.py`.