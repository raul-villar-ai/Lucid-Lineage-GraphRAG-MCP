"""
Lucid Lineage — Source Package.

Core modules:
  db          : Singleton Neo4j connection manager
  graph_tools : Unified Cypher query layer (canonical schema)
  agent       : LangChain orchestration, tool wrappers, graph memory
  llm         : Gemini chat-model factory (single source of truth for model config)
  mcp_server  : FastMCP server exposing tools via Model Context Protocol
  telemetry   : OpenTelemetry instrumentation (tool tracing + latency)
"""
