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

# Tool argument names that identify a Data_Asset. Used to work out which
# asset(s) a submission investigated so the dashboard traffic light can reflect
# THIS query rather than a static whole-graph scan.
_ASSET_ARG_KEYS = ("asset_name",)

# Tool argument names that identify a Compute_Node (a location). Turns that only
# investigate a location (e.g. blast-radius or compliance-boundary lookups) are
# resolved to the assets co-located there, so the traffic light still reflects
# something meaningful instead of going dark.
_LOCATION_ARG_KEYS = ("location_name", "compute_node")

# The full-graph leak audit tool. When a submission runs this, the correct
# per-submission status IS the whole-graph scan, so callers should fall back to
# security_status() instead of the asset-scoped variant.
_FULL_SCAN_TOOL = "audit_restricted_asset_leaks"


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
def audit_restricted_asset_leaks(classification: str = "") -> str:
    """Scans the ENTIRE graph for data assets that cross compliance boundaries.
    Detects assets stored or replicated across compute nodes governed by DIFFERENT
    compliance policies. This is the primary breach detection scan.
    Use this when asked to run a full compliance audit or check for data leaks.
    Optionally pass ``classification`` (e.g. 'Highly_Restricted') to scope the scan
    to one class; the tool then reports the DISTINCT-asset count for that class, so
    report that number exactly as stated rather than counting rows yourself."""
    return graph_tools.query_restricted_asset_leaks(classification or None)


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


def _extract_query_scope(intermediate_steps) -> tuple[list[str], list[str], bool]:
    """Inspect the agent's tool calls to work out what THIS submission investigated.

    Returns ``(touched_assets, touched_locations, full_scan_ran)`` where:
      * ``touched_assets``    — de-duplicated Data_Asset names passed to any tool
        this turn (order preserved), used for the asset-scoped traffic light.
      * ``touched_locations`` — de-duplicated Compute_Node names investigated this
        turn; the caller resolves these to their co-located assets so the light
        stays meaningful on location-only follow-ups instead of going dark.
      * ``full_scan_ran``     — True if the agent ran the whole-graph leak audit,
        in which case the caller should use the global ``security_status()``.

    ``intermediate_steps`` is the ``(AgentAction, observation)`` list returned by
    the AgentExecutor when ``return_intermediate_steps=True``.
    """
    touched_assets: list[str] = []
    touched_locations: list[str] = []
    full_scan_ran = False

    for step in intermediate_steps or []:
        # Each step is an (AgentAction, observation) tuple.
        action = step[0] if isinstance(step, (list, tuple)) and step else step
        tool_name = getattr(action, "tool", None)
        tool_input = getattr(action, "tool_input", None)

        if tool_name == _FULL_SCAN_TOOL:
            full_scan_ran = True

        if isinstance(tool_input, dict):
            for key in _ASSET_ARG_KEYS:
                value = tool_input.get(key)
                if isinstance(value, str) and value.strip():
                    touched_assets.append(value.strip())
            for key in _LOCATION_ARG_KEYS:
                value = tool_input.get(key)
                if isinstance(value, str) and value.strip():
                    touched_locations.append(value.strip())

    # De-duplicate while preserving first-seen order.
    touched_assets = list(dict.fromkeys(touched_assets))
    touched_locations = list(dict.fromkeys(touched_locations))
    return touched_assets, touched_locations, full_scan_ran


@trace_tool(name="agent_run_trace")
def run_trace(session_id, query, clearance, iam_role="Security_Analyst",
              agent_llm=None, return_details=False, **kwargs):
    """
    Execute a lineage trace using an AgentExecutor bound to Graph Tools.

    This is the primary entry point consumed by both the Streamlit UI (app.py)
    and the CLI terminal (main.py). The function signature is intentionally
    kept stable as a public contract.

    By default this returns the final answer as a plain string (unchanged
    behaviour for main.py). When ``return_details=True`` it instead returns a
    dict::

        {
            "answer":            <final answer string>,
            "touched_assets":    [<Data_Asset names this submission investigated>],
            "touched_locations": [<Compute_Node names this submission investigated>],
            "full_scan":         <True if the whole-graph leak audit ran this turn>,
        }

    so the dashboard can render a traffic light scoped to THIS submission rather
    than a static whole-graph scan.
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
        if return_details:
            return {"answer": mock_response, "touched_assets": [],
                    "touched_locations": [], "full_scan": False}
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
        # --- Write discipline: never mutate the graph unless explicitly asked ---
        "Only call log_audit_finding when the user EXPLICITLY asks you to log, record, or "
        "write a finding. Do NOT log a finding as an automatic side effect of tracing, "
        "identifying, or auditing — tracing and identifying are read-only actions. "
        # --- Answer the question that was actually asked ---
        "When the user asks about a specific data classification (e.g. 'Highly_Restricted'), "
        "restrict your answer AND any counts to assets of that exact classification; never "
        "report the unfiltered total as if it answered the narrower question. "
        "For a classification-scoped leak audit, pass that classification to "
        "audit_restricted_asset_leaks and report the DISTINCT-asset count exactly as the tool "
        "states it. "
        "Report counts as the number of DISTINCT affected assets, not the number of rows a "
        "tool returns — a single asset may appear in several rows. "
        # --- Ground findings strictly in retrieved data ---
        "When logging a finding, reference ONLY the compliance boundaries, policies, and "
        "relationships that appear in tool results you actually retrieved for that asset. "
        "Never attribute a boundary or policy to an asset unless a tool result shows that "
        "exact relationship. "
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
            return_intermediate_steps=True,  # needed to scope the security traffic light to this submission
        )

        result = agent_executor.invoke({
            "input": query,
            "chat_history": lc_history,
        })

        # Work out what this submission actually investigated BEFORE normalizing,
        # so the dashboard can show a per-query status instead of a static scan.
        touched_assets, touched_locations, full_scan = _extract_query_scope(
            result.get("intermediate_steps")
        )

        # Normalize before persisting/returning: Gemini may hand back a list of
        # content blocks, which is not a valid Neo4j primitive and would break
        # both graph memory and downstream display.
        final_output = _normalize_to_text(result.get("output", "Agent returned no output."))
        save_graph_memory(session_id, "assistant", final_output)

        if return_details:
            return {
                "answer": final_output,
                "touched_assets": touched_assets,
                "touched_locations": touched_locations,
                "full_scan": full_scan,
            }
        return final_output

    except Exception as e:
        error_msg = f"Agent invocation failed: {e}"
        log.error(error_msg, exc_info=True)
        if return_details:
            return {"answer": error_msg, "touched_assets": [],
                    "touched_locations": [], "full_scan": False}
        return error_msg