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
import re
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
# TOOL: Restricted Asset Leak Audit
# ═══════════════════════════════════════════════════════════════════════

@trace_tool()
def query_restricted_asset_leaks(classification: str | None = None) -> str:
    """Scan the entire graph for data assets that cross compliance boundaries.

    Detects assets stored or replicated across two DIFFERENT compute nodes that
    are governed by DIFFERENT compliance boundaries — the primary breach
    detection query.

    When ``classification`` is provided (e.g. ``"Highly_Restricted"``) the scan is
    restricted to assets of that exact classification and the summary reports the
    DISTINCT-asset count for that class, so callers receive the count as a stated
    fact instead of having to derive it from the raw rows.

    Correctness guards (both essential — see below):

      * ``c1 <> c2`` — the two compute nodes must be physically different. Without
        this, an asset sitting on a single node that is itself governed by more
        than one boundary (e.g. ``US_HQ_Mainframe_Vault`` is under BOTH
        ``Corporate_IP_Vault`` and ``SOX_Financial_Regs``) is mis-reported as a
        "leak" even though no data is crossing anywhere. That produced false
        positives like ``US_HQ_Mainframe_Vault -> US_HQ_Mainframe_Vault``.

      * ``c1.name < c2.name`` — canonical ordering so each offending node pair is
        returned exactly once. Without it the symmetric MATCH yields every leak
        twice (A->B and B->A are the same incident), which previously inflated
        the reported total (e.g. 20 rows for what is really a handful of assets).

    The headline count reports DISTINCT affected assets; the JSON detail still
    lists every offending node/boundary pairing for drill-down.
    """
    # Predicate intentionally differs from graph_admin's `c1 <> c2` (do NOT "unify"):
    # this tool lists one row per offending pair, so canonical `c1.name < c2.name`
    # returns each unordered pair once — `c1 <> c2` would duplicate them (A->B and B->A).
    query = """
    MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c1:Compute_Node)-[:GOVERNED_BY]->(b1:Compliance_Boundary)
    MATCH (d)-[:STORED_ON|REPLICATED_TO]->(c2:Compute_Node)-[:GOVERNED_BY]->(b2:Compliance_Boundary)
    WHERE c1.name < c2.name AND b1 <> b2
      AND ($classification IS NULL OR d.classification = $classification)
    RETURN DISTINCT
           d.name           AS asset,
           d.classification AS classification,
           c1.name          AS node_a,
           b1.name          AS boundary_a,
           b1.policy        AS policy_a,
           c2.name          AS node_b,
           b2.name          AS boundary_b,
           b2.policy        AS policy_b
    ORDER BY classification, asset, node_a, node_b
    """
    scope = f"{classification} " if classification else ""
    try:
        records = _run_read(query, classification=classification)
        if not records:
            return f"SUCCESS: No cross-boundary {scope}data leaks detected."
        distinct_assets = sorted({r["asset"] for r in records})
        return (
            f"ALERT: {len(distinct_assets)} {scope}asset(s) leaking across compliance "
            f"boundaries ({len(records)} boundary-crossing path(s) detected).\n"
            f"Leaking assets: {', '.join(distinct_assets)}\n"
            + json.dumps(records, indent=2)
        )
    except Exception as e:
        return f"Database query failed: {e}"


# ═══════════════════════════════════════════════════════════════════════
# TOOL: Location Name Resolver
# ═══════════════════════════════════════════════════════════════════════

@trace_tool()
def resolve_location(phrase: str) -> str:
    """Resolve a free-text location phrase to an EXACT Compute_Node name.

    The agent must call this before a location-based lookup whenever the user's
    wording is not already an exact node name, so it never silently guesses (e.g.
    resolving 'APAC gateway' to an analytics node instead of 'APAC_Edge_Gateway').

    Matching order:
      1. Exact, case-insensitive match -> return that name.
      2. Keyword match: score each node by how many of the phrase's word-tokens
         appear (as substrings) in the node name; the highest-scoring node wins
         IF it is unique.

    Returns exactly one of:
      * ``RESOLVED: <exact name>``                 - a single confident match
      * ``AMBIGUOUS: ... Candidates: a, b``         - several equally-good matches
      * ``NO MATCH ... Known compute nodes: ...``   - nothing matched
    """
    try:
        rows = _run_read("MATCH (c:Compute_Node) RETURN c.name AS name")
    except Exception as e:
        return f"Database query failed: {e}"
    names = [r["name"] for r in rows if r.get("name")]
    if not names:
        return "No compute nodes found in the graph."

    p = phrase.strip().lower()
    # 1. Exact, case-insensitive.
    for n in names:
        if n.lower() == p:
            return f"RESOLVED: {n}"

    # 2. Keyword/substring scoring on the phrase's word-tokens.
    tokens = [t for t in re.split(r"[^a-z0-9]+", p) if t]
    scored = [(sum(t in n.lower() for t in tokens), n) for n in names]
    scored = [(s, n) for s, n in scored if s > 0]
    if not scored:
        return f"NO MATCH for '{phrase}'. Known compute nodes: {', '.join(sorted(names))}."

    top = max(s for s, _ in scored)
    winners = sorted(n for s, n in scored if s == top)
    if len(winners) == 1:
        return f"RESOLVED: {winners[0]}"
    return (
        f"AMBIGUOUS: multiple compute nodes match '{phrase}'. "
        f"Candidates: {', '.join(winners)}. Ask the user to pick one exact name."
    )