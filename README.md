# Lucid Lineage

**Lucid Lineage** is an enterprise-grade sovereign data lineage and compliance AI agent[cite: 4]. Designed for highly regulated environments (public sector, finance), it maps secure infrastructure dependencies and autonomously enforces data boundary compliance using GraphRAG architecture[cite: 4].

## Project Summary
Moving beyond standard threat-triage engines, Lucid Lineage utilizes a **Neo4j knowledge graph** to trace data flows and identify compliance violations (e.g., GDPR, SOX, CCPA)[cite: 4]. It leverages a LangChain-orchestrated reasoning agent to traverse this graph, execute deterministic compliance tools, and log immutable audit findings back into the database[cite: 4].

## Codebase Guide

The system is a **GraphRAG compliance auditor**: a LangChain agent (backed by **Google Gemini**) reasons over a **Neo4j** knowledge graph, calls deterministic graph tools, and writes immutable audit findings back to the graph. At runtime a presentation entry point calls `run_trace()`, which lets the agent choose graph tools; those tools execute parameterized Cypher through a singleton driver against Neo4j.

```
app.py / main.py   →   run_trace()          →   Gemini selects tools
(presentation)         (src/agent.py)            │
                                                 src/graph_tools.py  →  src/db.py  →  Neo4j Aura
```

A core principle is **single-source-of-truth**: all Cypher lives in `src/graph_tools.py` (shared by the agent *and* the MCP server); all model configuration lives in `src/llm.py` (shared by the UI *and* the CLI).

### Presentation layer
* `app.py` — Streamlit web UI ("Forensic Workspace"): manages session state, the access-control sidebar (IAM role / clearance boundary), chat rendering, and per-prompt calls to `run_trace()`.
* `main.py` — CLI "Forensic Terminal": builds the live agent and loops over audit queries → `run_trace()` → prints results (with a Windows UTF-8 console guard).

### Orchestration layer
* `src/agent.py` — The core. Defines the six LangChain `@tool` wrappers, the Neo4j-backed chat memory (`get_graph_memory` / `save_graph_memory`, including primitive-serialization normalization), and `run_trace()` — the main pipeline (bounded history → role/clearance-aware prompt → `create_tool_calling_agent` + `AgentExecutor` with iteration/time caps → normalized, persisted answer). Falls back to a mock response when no LLM is supplied.
* `src/llm.py` — Gemini model factory and single source of truth for model configuration (`gemini-3.5-flash`, temperature 0, retries, timeout).

### Data access layer
* `src/graph_tools.py` — The unified Cypher query layer; all Neo4j business logic. Six tools: asset-lineage trace, co-location "blast radius", compliance-boundary check, write audit finding, retrieve past findings, and the cross-boundary leak scan. All queries are parameterized (injection-safe).
* `src/db.py` — Thread-safe singleton Neo4j driver (bounded connection pool + acquisition timeout), plus connectivity verification and graceful shutdown.

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
* `.env` — Secrets/config: Neo4j credentials, `GOOGLE_API_KEY`, `PROJECT_ID` (gitignored).
* `requirements.txt` — Python dependencies, aligned to the code's actual direct imports.
* `ARCHITECTURE.md`: Core system architecture, target state, and graph schema[cite: 3].
* `CLEANUP_LOG.md`: Housekeeping audit trail (what was reviewed/removed and why).

### Graph schema (quick reference)
* **Nodes:** `Data_Asset`, `Compute_Node`, `Compliance_Boundary`, `Service_Account`, `Audit_Finding` (plus `Session` / `Message` for chat memory).
* **Edges:** `STORED_ON`, `REPLICATED_TO`, `GOVERNED_BY`, `HAS_ACCESS`, `HAS_AUDIT_RECORD`.

## Setup Instructions
Create a `.env` file in the root directory[cite: 4]:
```env
NEO4J_URI=neo4j+s://<your-db-id>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your-password>
GOOGLE_API_KEY=<your-gemini-api-key>
```

Then install dependencies, seed the graph, and launch:
```bash
pip install -r requirements.txt
python seed_db.py            # provision / reset the Neo4j graph
streamlit run app.py         # web UI   (or:  python main.py  for the CLI)
```

Verify connectivity at any time with `python check_env.py` and `python check_models.py`.
