"""
Lucid Lineage — LangChain Agent Orchestration.

This module defines:
  1. LangChain @tool wrappers (thin facades over src.graph_tools)
  2. Neo4j-backed graph memory (session/message persistence)
  3. The `run_trace()` pipeline consumed by app.py and main.py
"""

import json
import logging
from langchain_core.tools import tool
# FIX: Restored correct package path to import AgentExecutor from langchain_classic
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from src.db import get_driver
from src import graph_tools
from src.telemetry import trace_tool

log = logging.getLogger("lucid_lineage.agent")

# Maximum number of historical messages to inject into the agent prompt.
# Prevents unbounded context growth on long-running sessions.
MAX_MEMORY_MESSAGES = 20


# ═══════════════════════════════════════════════════════════════════════
# LANGCHAIN TOOL WRAPPERS
# Thin facades — all query logic lives in src.graph_tools
# ═══════════════════════════════════════════════════════════════════════

@tool
def check_asset_lineage(asset_name: str) -> str:
    """Traces the full lineage of a data asset: storage locations, replications,
    compute node types, encryption levels, and governing compliance boundaries.
    Use this when asked about where data lives, how it flows, or what policies govern it."""
    return graph_tools.query_asset_lineage(asset_name)


@tool
def get_assets_in_location(location_name: str) -> str:
    """Finds all data assets stored or replicated to a specific compute node.
    Use this to determine the 'blast radius' — what else shares a server or storage bucket."""
    return graph_tools.query_assets_in_location(location_name)


@tool
def check_compliance_boundary(compute_node: str) -> str:
    """Checks the sovereignty and compliance boundaries governing a compute node.
    Use this when asked about what policies or regulations apply to a specific server."""
    return graph_tools.query_compliance_boundary(compute_node)


@tool
def log_audit_finding(asset_name: str, finding_type: str, details: str) -> str:
    """Logs an immutable compliance finding or security alert to the knowledge graph.
    Use this to record breaches, warnings, or verification results against an asset."""
    return graph_tools.write_audit_finding(asset_name, finding_type, details)


@tool
def retrieve_past_findings(asset_name: str) -> str:
    """Retrieves historical audit findings previously logged for this asset.
    Use this to check if issues have already been flagged or to review audit history."""
    return graph_tools.query_past_findings(asset_name)


@tool
def audit_restricted_asset_leaks() -> str:
    """Scans the ENTIRE graph for data assets that cross compliance boundaries.
    Detects assets stored or replicated across compute nodes governed by DIFFERENT
    compliance policies. This is the primary breach detection scan.
    Use this when asked to run a full compliance audit or check for data leaks."""
    return graph_tools.query_restricted_asset_leaks()


# ═══════════════════════════════════════════════════════════════════════
# GRAPH MEMORY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

def _normalize_to_text(content) -> str:
    """Coerce arbitrary agent/LLM output into a primitive string.

    LangChain + Gemini may return message content as a plain string, a list of
    content-block dicts (e.g. ``[{"type": "text", "text": "..."}]``), or a dict.
    Neo4j node properties may only hold primitives (or arrays thereof), so any
    non-string value MUST be flattened before it is persisted as a
    ``Message.content`` property — otherwise the driver raises
    ``Property values can only be of primitive types or arrays thereof`` and the
    memory write is silently dropped. Centralizing this here also guarantees the
    CLI (main.py) and Streamlit UI (app.py) both receive a clean string.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float, bool)):
        return str(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content")
                parts.append(text if isinstance(text, str) else json.dumps(block, default=str))
            elif isinstance(block, str):
                parts.append(block)
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        text = content.get("text") or content.get("output")
        return text if isinstance(text, str) else json.dumps(content, default=str)
    return str(content)


def get_graph_memory(session_id: str, limit: int = MAX_MEMORY_MESSAGES) -> list[dict]:
    """Retrieve the most recent messages for a session from Neo4j.

    Returns messages in chronological order, capped at `limit` to prevent
    prompt window bloat on long-running sessions.
    """
    query = """
    MATCH (s:Session {id: $session_id})-[:HAS_MESSAGE]->(m:Message)
    RETURN m.role AS role, m.content AS content
    ORDER BY m.timestamp DESC
    LIMIT $limit
    """
    try:
        with get_driver().session() as session:
            result = session.run(query, session_id=session_id, limit=limit)
            records = [record.data() for record in result]
            # Reverse to restore chronological order (queried DESC for LIMIT)
            return list(reversed(records)) if records else []
    except Exception as e:
        log.warning("Failed to read graph memory for session %s: %s", session_id, e)
        return []


def save_graph_memory(session_id: str, role: str, content: str) -> None:
    """Persist a message to the session's graph memory.

    Content is truncated at 4000 characters to prevent graph bloat from
    excessively long agent responses.
    """
    # Guarantee a primitive string — Neo4j rejects list/dict property values.
    content = _normalize_to_text(content)

    max_content_len = 4000
    if len(content) > max_content_len:
        content = content[:max_content_len] + "\n... [truncated]"

    query = """
    MERGE (s:Session {id: $session_id})
    CREATE (m:Message {role: $role, content: $content, timestamp: timestamp()})
    MERGE (s)-[:HAS_MESSAGE]->(m)
    """
    try:
        with get_driver().session() as session:
            session.run(query, session_id=session_id, role=role, content=content)
    except Exception as e:
        log.error("Failed to write memory to graph for session %s: %s", session_id, e)


# ═══════════════════════════════════════════════════════════════════════
# AGENTIC ROUTING PIPELINE
# ═══════════════════════════════════════════════════════════════════════

# Complete tool registry — single source of truth
TOOLS = [
    check_asset_lineage,
    get_assets_in_location,
    check_compliance_boundary,
    log_audit_finding,
    retrieve_past_findings,
    audit_restricted_asset_leaks,
]


@trace_tool(name="agent_run_trace")
def run_trace(session_id, query, clearance, iam_role="Security_Analyst", agent_llm=None, **kwargs):
    """
    Execute a lineage trace using an AgentExecutor bound to Graph Tools.

    This is the primary entry point consumed by both the Streamlit UI (app.py)
    and the CLI terminal (main.py). The function signature is intentionally
    kept stable as a public contract.
    """
    # 1. Load bounded chat history from the graph
    raw_history = get_graph_memory(session_id)
    lc_history = []
    for msg in raw_history:
        if msg["role"] == "user":
            lc_history.append(HumanMessage(content=msg["content"]))
        else:
            lc_history.append(AIMessage(content=msg["content"]))

    # 2. Persist the incoming user query
    save_graph_memory(session_id, "user", query)

    # 3. Mock fallback when no LLM is provided (e.g., offline testing)
    if not agent_llm:
        mock_response = f"[Mock] No LLM provided. Query received: {query}"
        save_graph_memory(session_id, "assistant", mock_response)
        return mock_response

    # 4. Build the agent prompt with role-based context
    system_instruction = (
        f"You are an active compliance auditing agent operating as a {iam_role} "
        f"with clearance level: {clearance}. "
        "You are connected to a Neo4j enterprise knowledge graph containing data assets, "
        "compute nodes, compliance boundaries, and service accounts. "
        "ALWAYS use your tools to pull deterministic infrastructure data before answering. "
        "Do NOT guess or hallucinate graph data. "
        "Provide brief, executive-level summaries using bullet points. "
        "If you discover data replicating to a foreign jurisdiction or crossing "
        "compliance boundaries, explicitly flag the SOVEREIGN BOUNDARY BREACH. "
        "Node and asset names are EXACT, case-sensitive identifiers (e.g. 'APAC_Edge_Gateway', "
        "not 'APAC gateway'). If a lookup returns no results, do NOT repeatedly guess name "
        "variations — reason from the data you already have or run a broader scan instead. "
        "Once you have gathered enough information to answer, STOP calling tools and provide "
        "your final summary."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_instruction),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # 5. Create and execute the agent
    try:
        agent = create_tool_calling_agent(agent_llm, TOOLS, prompt)

        agent_executor = AgentExecutor(
            agent=agent,
            tools=TOOLS,
            verbose=True,
            max_iterations=20,
            max_execution_time=120,  # wall-clock cap: stop gracefully before upstream timeouts/disconnects
            handle_parsing_errors=True,
            early_stopping_method="force", # PATCHED: Set to 'force' to prevent legacy termination loops from crashing
        )

        result = agent_executor.invoke({
            "input": query,
            "chat_history": lc_history,
        })

        # Normalize before persisting/returning: Gemini may hand back a list of
        # content blocks, which is not a valid Neo4j primitive and would break
        # both graph memory and downstream display.
        final_output = _normalize_to_text(result.get("output", "Agent returned no output."))
        save_graph_memory(session_id, "assistant", final_output)
        return final_output

    except Exception as e:
        error_msg = f"Agent invocation failed: {e}"
        log.error(error_msg, exc_info=True)
        return error_msg