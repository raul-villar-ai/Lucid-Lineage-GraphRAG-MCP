"""
Lucid Lineage — FastMCP Server.

Exposes the unified graph tools via the Model Context Protocol (MCP) for
standardized tool bridging. All query logic is imported from src.graph_tools,
ensuring this server and the LangChain agent always use identical Cypher
queries and the same canonical graph schema.
"""

from fastmcp import FastMCP
from src import graph_tools

mcp = FastMCP("LucidLineage_Neo4j_Connector")


@mcp.tool()
def trace_asset_lineage(asset_name: str) -> str:
    """Traces the full lineage of a data asset including storage, replication,
    encryption, and compliance governance."""
    return graph_tools.query_asset_lineage(asset_name)


@mcp.tool()
def get_assets_in_location(location_name: str) -> str:
    """Finds all data assets stored or replicated to a specific compute node.
    Use this to determine the blast radius of a compromised server."""
    return graph_tools.query_assets_in_location(location_name)


@mcp.tool()
def check_compliance_boundary(compute_node: str) -> str:
    """Checks the sovereignty and compliance boundaries governing a compute node."""
    return graph_tools.query_compliance_boundary(compute_node)


@mcp.tool()
def log_audit_finding(asset_name: str, finding_type: str, details: str) -> str:
    """Logs an immutable compliance finding to the knowledge graph.

    This is a WRITE that mutates the graph. Call it ONLY when the user explicitly
    asks to log, record, or write a finding. Do NOT log a finding as an automatic
    side effect of tracing, identifying, or auditing — those are read-only actions.
    (Mirrors the write-discipline enforced in the LangChain agent's system prompt.)"""
    return graph_tools.write_audit_finding(asset_name, finding_type, details)


@mcp.tool()
def retrieve_past_findings(asset_name: str) -> str:
    """Retrieves historical audit findings previously logged for an asset."""
    return graph_tools.query_past_findings(asset_name)


@mcp.tool()
def audit_restricted_asset_leaks(classification: str = "") -> str:
    """Scans the entire graph for data assets crossing compliance boundaries.
    This is the primary breach detection scan — use for full compliance audits.
    Optionally pass a classification (e.g. 'Highly_Restricted') to scope the scan;
    the summary then reports the distinct-asset count for that class."""
    return graph_tools.query_restricted_asset_leaks(classification or None)


if __name__ == "__main__":
    mcp.run()