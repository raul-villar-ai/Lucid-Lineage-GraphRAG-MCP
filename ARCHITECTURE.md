# Lucid Lineage: Reference Architecture & Execution Plan

> **Personal Project Notice.** Lucid Lineage is an independent, open-source personal research project built entirely in my own time using public libraries, in an individual capacity for learning and brand-building. It does not reflect the views, strategies, or technologies of any current or past employers, and no corporate time, hardware, or intellectual property was used in its making. All data is synthetic. Released under the MIT License — see [`LICENSE`](LICENSE). © 2026 Raul Villar Robledo.

## 1. Vision & Core Philosophy
Lucid Lineage maps air-gapped infrastructure dependencies and enforces data boundary compliance. The system decouples backend infrastructure from cognitive reasoning, allowing an autonomous AI agent to navigate an enterprise Neo4j knowledge graph, trace data flows, identify compliance violations, and mathematically log every reasoning step into a persistent audit ledger.

## 2. Current State (Phase 1: Working PoC)
The project currently successfully demonstrates a localized GraphRAG architecture:

* **The Graph:** A fully modeled enterprise schema in Neo4j comprising `Compliance_Boundary`, `Compute_Node`, `Data_Asset`, and `Service_Account` nodes.
* **The Agent:** A LangChain `create_tool_calling_agent` that maintains chat history inside the Neo4j graph as `Session` and `Message` nodes. Each turn also surfaces the assets and compute nodes it investigated (`touched_assets` / `touched_locations` / `full_scan`) via `run_trace(..., return_details=True)`, so the presentation layer can scope feedback to the current submission.
* **The Tools:** Unified in `src/graph_tools.py`, consumed by both LangChain and MCP:
  * `check_asset_lineage` — Traces storage nodes, replications, encryption, and compliance boundaries.
  * `get_assets_in_location` — Determines "blast radius" of co-located assets.
  * `check_compliance_boundary` — Checks sovereignty policies governing a compute node.
  * `log_audit_finding` — Writes an immutable `Audit_Finding` directly to the graph.
  * `retrieve_past_findings` — Reads historical audit records for an asset.
  * `audit_restricted_asset_leaks` — Full-graph scan detecting assets that cross compliance boundaries. Requires the two compute nodes to be physically distinct (`c1 <> c2`) and applies a canonical ordering (`c1.name < c2.name`), so a single node governed by multiple boundaries is not mis-reported as a leak and each incident is counted once; results are reported as distinct affected assets.
* **Per-submission security posture:** A RED/AMBER/GREEN "traffic light" in the UI reflects the *last query's* result rather than a static whole-graph scan. `src/graph_admin.py` provides a whole-graph scan (`security_status`) for full audits and an asset-scoped scan (`security_status_for_assets`) resolved from the touched assets/locations of the submission, both sharing one classification helper.
* **Live knowledge-graph visualization:** A dedicated Streamlit tab (`src/graph_view.py`, Cytoscape.js via `st-link-analysis`) renders the graph and highlights the subgraph the last query touched. The base graph is queried once and cached; each submission only recomputes the highlight, and the keyed component reconciles in place with no reload or re-query.
* **Observability:** OpenTelemetry instrumentation (`src/telemetry.py`) traces `run_trace` and every graph tool (spans, latency, success/failure, non-secret arguments).

## 3. Architecture Layers

```text
┌──────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                    │
│                                                          │
│       ┌──────────────┐        ┌───────────────┐          │
│       │ Streamlit UI │        │ CLI Terminal  │          │
│       │   (app.py)   │        │   (main.py)   │          │
│       │  ┌────────┐  │        └───────┬───────┘          │
│       │  │ Graph  │  │                │                  │
│       │  │  tab   │──┼── src/graph_view.py (read-only)   │
│       │  └────────┘  │                │                  │
│       └──────┬───────┘                │                  │
│              └───────────┬────────────┘                  │
├──────────────────────────┼───────────────────────────────┤
│                          │                               │
│                  ORCHESTRATION LAYER                     │
│                          │                               │
│             ┌────────────▼────────────┐                  │
│             │ LangChain AgentExecutor │                  │
│             │     (src/agent.py)      │                  │
│             └────────────┬────────────┘                  │
│                          │                               │
│             ┌────────────▼────────────┐                  │
│             │      FastMCP Server     │                  │
│             │   (src/mcp_server.py)   │                  │
│             └────────────┬────────────┘                  │
├──────────────────────────┼───────────────────────────────┤
│                          │                               │
│                   DATA ACCESS LAYER                      │
│                          │                               │
│             ┌────────────▼────────────┐                  │
│             │   Unified Graph Tools   │                  │
│             │  (src/graph_tools.py)   │◄─ src/graph_admin.py
│             └────────────┬────────────┘   (health, security scans)
│                          │                               │
│             ┌────────────▼────────────┐                  │
│             │  Singleton DB Manager   │                  │
│             │       (src/db.py)       │                  │
│             └────────────┬────────────┘                  │
├──────────────────────────┼───────────────────────────────┤
│                          │                               │
│                   PERSISTENCE LAYER                      │
│                          │                               │
│             ┌────────────▼────────────┐                  │
│             │  Neo4j Knowledge Graph  │                  │
│             │    (Aura DB / Local)    │                  │
│             └─────────────────────────┘                  │
└──────────────────────────────────────────────────────────┘

```

The Knowledge Graph tab reads the graph read-only through the singleton driver (`src/db.py`) and caches the result; it is a visualization surface and is not part of the agent's write path.

## 4. Target State & Execution Plan (Phase 2 & 3)

### Milestone A: Unification of the Tooling Layer ✅ COMPLETE

Tool logic has been consolidated into `src/graph_tools.py`. Both the LangChain agent and MCP server are now thin facades importing from this single source of truth. Schema mismatch resolved — all queries use the canonical schema.

### Milestone B: Enhanced Observability & Tracing ✅ COMPLETE

OpenTelemetry is integrated natively via `src/telemetry.py`. The `trace_tool` decorator records spans, non-secret arguments, latency, and success/failure for `run_trace` and each graph tool, providing granular operational metrics (tool calls, latency, success rate) as a foundation for usage and cost monitoring.

### Milestone C: Cloud Native Deployment Readiness

* **Execution:** Prepare the codebase for deployment via Vertex AI Agent Engine.
* **IaC Integration:** Scaffold Terraform configuration files to automate the provisioning of the Vertex AI, Neo4j, and Streamlit hosting environments.
* **Access Management:** Integrate Google Cloud IAM principles (currently simulated via a `"SC_Cleared"` clearance parameter) to enforce zero-trust execution at the tool level.

### Milestone D: Per-Submission Feedback & Graph Visualization ✅ COMPLETE

* **Per-submission security posture:** The RED/AMBER/GREEN traffic light reflects the specific submission (scoped to the assets/locations it investigated, or the whole graph on a full audit) instead of a static scan, and changes turn to turn.
* **Leak-detection correctness:** The cross-boundary leak scan no longer double-counts incidents or mis-reports single multi-governed nodes as leaks; it reports distinct affected assets.
* **Interactive knowledge graph:** A dedicated, dynamically-highlighting graph tab (Cytoscape.js via `st-link-analysis`) that updates as the conversation progresses without reload or re-query.

## 5. Data Schema Definition

The graph models a highly regulated public-sector data environment.

**Core Nodes:**

* `Data_Asset` (e.g., EU_Customer_PII_Master)
* `Compute_Node` (e.g., EU_Frankfurt_Cloud_01)
* `Compliance_Boundary` (e.g., GDPR_EU_Privacy)
* `Service_Account` (e.g., SVC_ETL_EU_Sync)

**Core Edges:**

* `(Data_Asset)-[:STORED_ON|REPLICATED_TO]->(Compute_Node)`
* `(Compute_Node)-[:GOVERNED_BY]->(Compliance_Boundary)`
* `(Service_Account)-[:HAS_ACCESS]->(Data_Asset)`
* `(Data_Asset)-[:HAS_AUDIT_RECORD]->(Audit_Finding)`