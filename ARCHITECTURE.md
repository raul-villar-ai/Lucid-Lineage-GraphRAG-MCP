# Lucid Lineage: Reference Architecture & Execution Plan

## 1. Vision & Core Philosophy
Lucid Lineage maps air-gapped infrastructure dependencies and enforces data boundary compliance. The system decouples backend infrastructure from cognitive reasoning, allowing an autonomous AI agent to navigate an enterprise Neo4j knowledge graph, trace data flows, identify compliance violations, and mathematically log every reasoning step into a persistent audit ledger.

## 2. Current State (Phase 1: Working PoC)
The project currently successfully demonstrates a localized GraphRAG architecture:

* **The Graph:** A fully modeled enterprise schema in Neo4j comprising `Compliance_Boundary`, `Compute_Node`, `Data_Asset`, and `Service_Account` nodes.
* **The Agent:** A LangChain `create_tool_calling_agent` that maintains chat history inside the Neo4j graph as `Session` and `Message` nodes.
* **The Tools:** Unified in `src/graph_tools.py`, consumed by both LangChain and MCP:
  * `check_asset_lineage` — Traces storage nodes, replications, encryption, and compliance boundaries.
  * `get_assets_in_location` — Determines "blast radius" of co-located assets.
  * `check_compliance_boundary` — Checks sovereignty policies governing a compute node.
  * `log_audit_finding` — Writes an immutable `Audit_Finding` directly to the graph.
  * `retrieve_past_findings` — Reads historical audit records for an asset.
  * `audit_restricted_asset_leaks` — Full-graph scan detecting assets that cross compliance boundaries.

## 3. Architecture Layers

```text
┌──────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                    │
│                                                          │
│       ┌──────────────┐        ┌───────────────┐          │
│       │ Streamlit UI │        │ CLI Terminal  │          │
│       │   (app.py)   │        │   (main.py)   │          │
│       └──────┬───────┘        └───────┬───────┘          │
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
│             │  (src/graph_tools.py)   │                  │
│             └────────────┬────────────┘                  │
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

## 4. Target State & Execution Plan (Phase 2 & 3)

### Milestone A: Unification of the Tooling Layer ✅ COMPLETE

Tool logic has been consolidated into `src/graph_tools.py`. Both the LangChain agent and MCP server are now thin facades importing from this single source of truth. Schema mismatch resolved — all queries use the canonical schema.

### Milestone B: Enhanced Observability & Tracing

* **Execution:** Integrate OpenTelemetry natively to provide deep usage monitoring (tracking API quota limits, overall system utilization, and computational costs) alongside granular operational metrics (tracing tool calls, latency, and token consumption).

### Milestone C: Cloud Native Deployment Readiness

* **Execution:** Prepare the codebase for deployment via Vertex AI Agent Engine.
* **IaC Integration:** Scaffold Terraform configuration files to automate the provisioning of the Vertex AI, Neo4j, and Streamlit hosting environments.
* **Access Management:** Integrate Google Cloud IAM principles (currently simulated via a `"SC_Cleared"` clearance parameter) to enforce zero-trust execution at the tool level.

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
