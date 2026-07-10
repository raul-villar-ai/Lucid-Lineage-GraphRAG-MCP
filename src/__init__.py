"""
Lucid Lineage — Source Package.

Core modules:
  db          : Singleton Neo4j connection manager
  graph_tools : Unified Cypher query layer (canonical schema)
  graph_admin : Graph seed/reset, drift detection, security traffic light
  agent       : LangChain orchestration, tool wrappers, graph memory
  llm         : LLM factory — Google Gemini / OpenAI toggle (single source of truth for model config)
  mcp_server  : FastMCP server exposing tools via Model Context Protocol
  graph_view  : Knowledge-graph visualization tab (st-link-analysis / Cytoscape.js)
  telemetry   : OpenTelemetry instrumentation (tool tracing + latency)
"""
