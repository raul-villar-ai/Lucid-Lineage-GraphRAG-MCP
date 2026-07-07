"""
Lucid Lineage — Unified Graph Query Layer.

All Neo4j business logic lives here. Both the LangChain agent (@tool wrappers
in agent.py) and the MCP server (@mcp.tool wrappers in mcp_server.py) import
these functions, ensuring a single source of truth for Cypher queries.

Canonical Schema (from data/init_graph.cypher):
  Nodes:  Data_Asset, Compute_Node, Compliance_Boundary, Service_Account
  Edges:  STORED_ON, REPLICATED_TO, GOVERNED_BY, HAS_ACCESS, HAS_AUDIT_RECORD
"""

import json
import logging
from src.db import get_driver
from src.telemetry import trace_tool

log = logging.getLogger("lucid_lineage.graph_tools")


# ─── Internal Helpers ──────────────────────────────────────────────────

def _run_read(query: str, **params) -> list[dict]:
    """Execute a read transaction and return a list of record dicts."""
    try:
        with get_driver().session() as session:
            result = session.run(query, **params)
            return [record.data() for record in result]
    except Exception as e:
        log.error("Read query failed: %s | Params: %s | Error: %s", query.strip()[:80], params, e)
        raise


def _run_write(query: str, **params) -> dict | None:
    """Execute a write transaction and return the first record (or None)."""
    try:
        with get_driver().session() as session:
            result = session.run(query, **params)
            record = result.single()
            return record.data() if record else None
    except Exception as e:
        log.error("Write query failed: %s | Params: %s | Error: %s", query.strip()[:80], params, e)
        raise


# ═══════════════════════════════════════════════════════════════════════
# TOOL: Asset Lineage Trace
# ═══════════════════════════════════════════════════════════════════════

@trace_tool()
def query_asset_lineage(asset_name: str) -> str:
    """Trace where a data asset is stored/replicated, including compliance governance.
    
    Returns compute nodes, their types, encryption levels, and the compliance
    boundaries that govern each node.
    """
    query = """
    MATCH (d:Data_Asset {name: $asset_name})-[action:STORED_ON|REPLICATED_TO]->(c:Compute_Node)
    OPTIONAL MATCH (c)-[:GOVERNED_BY]->(b:Compliance_Boundary)
    RETURN type(action) AS action,
           c.name        AS compute_node,
           c.type        AS compute_type,
           c.encryption  AS encryption,
           b.name        AS compliance_boundary,
           b.policy      AS policy
    """
    try:
        records = _run_read(query, asset_name=asset_name)
        if not records:
            return f"No lineage data found for asset: {asset_name}"
        return json.dumps(records, indent=2)
    except Exception as e:
        return f"Database query failed: {e}"


# ═══════════════════════════════════════════════════════════════════════
# TOOL: Blast Radius / Co-located Assets
# ═══════════════════════════════════════════════════════════════════════

@trace_tool()
def query_assets_in_location(location_name: str) -> str:
    """Find all data assets stored or replicated to a specific compute node."""
    query = """
    MATCH (d:Data_Asset)-[action:STORED_ON|REPLICATED_TO]->(c:Compute_Node {name: $location_name})
    RETURN d.name           AS asset_name,
           d.classification AS classification,
           type(action)     AS relationship
    """
    try:
        records = _run_read(query, location_name=location_name)
        if not records:
            return f"No assets found on compute node: {location_name}"
        return json.dumps(records, indent=2)
    except Exception as e:
        return f"Database query failed: {e}"


# ═══════════════════════════════════════════════════════════════════════
# TOOL: Compliance Boundary Check
# ═══════════════════════════════════════════════════════════════════════

@trace_tool()
def query_compliance_boundary(compute_node: str) -> str:
    """Check the sovereignty and compliance boundaries governing a compute node."""
    query = """
    MATCH (c:Compute_Node {name: $compute_node})-[:GOVERNED_BY]->(b:Compliance_Boundary)
    RETURN b.name   AS boundary_name,
           b.policy AS policy,
           b.tier   AS tier
    """
    try:
        records = _run_read(query, compute_node=compute_node)
        if not records:
            return f"WARNING: Compute node '{compute_node}' has no mapped compliance boundaries."
        return json.dumps(records, indent=2)
    except Exception as e:
        return f"Database query failed: {e}"


# ═══════════════════════════════════════════════════════════════════════
# TOOL: Audit Finding Logger
# ═══════════════════════════════════════════════════════════════════════

@trace_tool()
def write_audit_finding(asset_name: str, finding_type: str, details: str) -> str:
    """Log an immutable compliance finding to the knowledge graph.
    
    Creates an Audit_Finding node linked to the target Data_Asset via
    a HAS_AUDIT_RECORD relationship.
    """
    query = """
    MATCH (d:Data_Asset {name: $asset_name})
    CREATE (f:Audit_Finding {
        type:      $finding_type,
        details:   $details,
        timestamp: datetime(),
        immutable: true
    })
    CREATE (d)-[:HAS_AUDIT_RECORD]->(f)
    RETURN d.name AS asset, f.type AS finding_type, toString(f.timestamp) AS logged_at
    """
    try:
        record = _run_write(query, asset_name=asset_name, finding_type=finding_type, details=details)
        if record:
            return (
                f"SUCCESS: Audit finding logged: [{record['finding_type']}] "
                f"on {record['asset']} at {record['logged_at']}"
            )
        return f"ERROR: Asset '{asset_name}' not found in the graph. Cannot log finding."
    except Exception as e:
        return f"Database write failed: {e}"


# ═══════════════════════════════════════════════════════════════════════
# TOOL: Retrieve Past Findings
# ═══════════════════════════════════════════════════════════════════════

@trace_tool()
def query_past_findings(asset_name: str) -> str:
    """Retrieve historical audit findings previously logged for this asset."""
    query = """
    MATCH (d:Data_Asset {name: $asset_name})-[:HAS_AUDIT_RECORD]->(f:Audit_Finding)
    RETURN f.type           AS finding_type,
           f.details        AS details,
           toString(f.timestamp) AS timestamp
    ORDER BY f.timestamp DESC
    LIMIT 10
    """
    try:
        records = _run_read(query, asset_name=asset_name)
        if not records:
            return f"No prior audit findings recorded for '{asset_name}'."
        return json.dumps(records, indent=2)
    except Exception as e:
        return f"Database query failed: {e}"


# ═══════════════════════════════════════════════════════════════════════
# TOOL: Restricted Asset Leak Audit (NEWLY IMPLEMENTED)
# ═══════════════════════════════════════════════════════════════════════

@trace_tool()
def query_restricted_asset_leaks() -> str:
    """Scan the entire graph for data assets that cross compliance boundaries.

    Detects assets stored or replicated across compute nodes governed by
    DIFFERENT compliance policies — the primary breach detection query.
    Referenced in ARCHITECTURE.md but previously unimplemented.
    """
    query = """
    MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c1:Compute_Node)-[:GOVERNED_BY]->(b1:Compliance_Boundary)
    MATCH (d)-[:STORED_ON|REPLICATED_TO]->(c2:Compute_Node)-[:GOVERNED_BY]->(b2:Compliance_Boundary)
    WHERE b1 <> b2
    RETURN DISTINCT
           d.name           AS asset,
           d.classification AS classification,
           c1.name          AS node_a,
           b1.name          AS boundary_a,
           b1.policy        AS policy_a,
           c2.name          AS node_b,
           b2.name          AS boundary_b,
           b2.policy        AS policy_b
    """
    try:
        records = _run_read(query)
        if not records:
            return "SUCCESS: No cross-boundary data leaks detected."
        return (
            f"ALERT: {len(records)} cross-boundary leak(s) detected.\n"
            + json.dumps(records, indent=2)
        )
    except Exception as e:
        return f"Database query failed: {e}"
