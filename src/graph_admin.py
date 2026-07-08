"""
Lucid Lineage — Graph Administration & Health.

Shared helpers for:
  * (re)seeding the Neo4j graph from the canonical ``data/init_graph.cypher``,
  * detecting whether the graph has drifted from that pristine seed state, and
  * computing a deterministic security "traffic light" for the dashboard.

All functions use the singleton driver from ``src.db`` (one shared pool), so the
Streamlit UI, the CLI, and the standalone seeder all behave identically.
"""

import os
import re
import hashlib
import logging

from src.db import get_driver

log = logging.getLogger("lucid_lineage.graph_admin")

# Canonical seed script — resolved relative to the project root so this works
# regardless of the caller's current working directory.
SEED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "init_graph.cypher",
)

# Internal bookkeeping label for the baseline-signature node. Excluded from every
# fingerprint and from user-facing counts.
_BASELINE_LABEL = "_GraphBaseline"

# Labels that represent transient runtime state (conversation memory), not the
# modeled infrastructure — excluded from drift detection.
_TRANSIENT_LABELS = ["Session", "Message", _BASELINE_LABEL]

# Classifications considered sensitive for the security scan.
_SENSITIVE = ["Highly_Restricted", "Restricted"]

# Encryption levels considered weak for sensitive data.
_WEAK_ENCRYPTION = ["Standard", "Transit_Only"]


# ─── Seeding / Reset ────────────────────────────────────────────────────

def _split_statements(cypher_text: str) -> list[str]:
    """Strip ``//`` comments then split a multi-statement script on ``;``."""
    no_comments = re.sub(r"//.*", "", cypher_text)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def reset_graph() -> dict:
    """Wipe and re-seed the graph from ``data/init_graph.cypher``.

    After seeding, capture a baseline fingerprint in a singleton
    ``_GraphBaseline`` node so later drift can be detected. Returns a summary
    dict: ``{statements_executed, errors, baseline}``.
    """
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        statements = _split_statements(f.read())

    executed, errors = 0, []
    with get_driver().session() as session:
        for stmt in statements:
            try:
                session.run(stmt)
                executed += 1
            except Exception as e:  # keep going; report per-statement failures
                first_line = str(e).splitlines()[0]
                errors.append(first_line)
                log.error("Seed statement failed: %s | %s", stmt[:80], first_line)

    signature = _compute_fingerprint()
    _store_baseline(signature)

    summary = {"statements_executed": executed, "errors": errors, "baseline": signature[:12]}
    log.info("Graph reset complete: %s", summary)
    return summary


# ─── Drift detection ────────────────────────────────────────────────────

def _compute_fingerprint() -> str:
    """SHA-256 fingerprint of the modeled graph (domain nodes + relationships).

    Includes domain nodes (label + name) and relationships (type + endpoint
    names), plus any ``Audit_Finding`` nodes, so a newly logged finding counts as
    a modification. Excludes transient chat memory and the baseline node itself.
    """
    with get_driver().session() as session:
        node_rows = session.run(
            """
            MATCH (n)
            WHERE none(l IN labels(n) WHERE l IN $transient)
            RETURN labels(n)[0] AS label, coalesce(n.name, '<unnamed>') AS name
            ORDER BY label, name
            """,
            transient=_TRANSIENT_LABELS,
        ).data()
        rel_rows = session.run(
            """
            MATCH (a)-[r]->(b)
            WHERE none(l IN labels(a) WHERE l IN $transient)
              AND none(l IN labels(b) WHERE l IN $transient)
            RETURN type(r) AS t, coalesce(a.name, '') AS an, coalesce(b.name, '') AS bn
            ORDER BY t, an, bn
            """,
            transient=_TRANSIENT_LABELS,
        ).data()

    parts = [f"N|{r['label']}|{r['name']}" for r in node_rows]
    parts += [f"R|{r['t']}|{r['an']}->{r['bn']}" for r in rel_rows]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _store_baseline(signature: str) -> None:
    with get_driver().session() as session:
        session.run(
            f"""
            MERGE (b:{_BASELINE_LABEL} {{id: 'singleton'}})
            SET b.signature = $sig, b.captured_at = timestamp()
            """,
            sig=signature,
        )


def get_baseline_signature() -> str | None:
    """Return the stored baseline signature, or None if none was captured."""
    with get_driver().session() as session:
        rec = session.run(
            f"MATCH (b:{_BASELINE_LABEL} {{id: 'singleton'}}) RETURN b.signature AS sig"
        ).single()
    return rec["sig"] if rec else None


def is_graph_modified() -> bool | None:
    """True/False whether the graph differs from the captured baseline.

    Returns None when no baseline exists yet (e.g. the graph was seeded without
    one) — the caller should prompt the user to run a reset.
    """
    baseline = get_baseline_signature()
    if baseline is None:
        return None
    try:
        return _compute_fingerprint() != baseline
    except Exception as e:
        log.warning("Fingerprint comparison failed: %s", e)
        return None


# ─── Security traffic light ─────────────────────────────────────────────

def _classify(leaks: int, ungoverned: int, weak_enc: int) -> dict:
    """Map raw security counts onto the RED/AMBER/GREEN traffic-light dict.

    Shared by both the whole-graph scan (``security_status``) and the
    per-submission scoped scan (``security_status_for_assets``) so the two can
    never drift apart.
    """
    cautions = int(ungoverned) + int(weak_enc)
    if int(leaks) > 0:
        level = "RED"
    elif cautions > 0:
        level = "AMBER"
    else:
        level = "GREEN"

    return {
        "level": level,
        "leaks": int(leaks),
        "ungoverned_assets": int(ungoverned),
        "weak_encryption_assets": int(weak_enc),
    }


def security_status() -> dict:
    """Deterministic security 'traffic light' from a live WHOLE-GRAPH scan.

    * RED   — cross-boundary data leaks exist (an asset sits on compute nodes
              governed by *different* compliance boundaries).
    * AMBER — caution signals only: sensitive data on an ungoverned node, or
              sensitive data under weak encryption. Possible issue, unconfirmed.
    * GREEN — no leaks and no caution signals.

    This scans the ENTIRE graph, so its result is invariant to any individual
    chat query — use it for the "run a full audit" case. For a status that
    reflects the specific asset(s) a submission investigated, use
    ``security_status_for_assets`` instead.

    Returns ``{level, leaks, ungoverned_assets, weak_encryption_assets}``.
    """
    with get_driver().session() as session:
        leaks = session.run(
            """
            MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c1:Compute_Node)-[:GOVERNED_BY]->(b1:Compliance_Boundary)
            MATCH (d)-[:STORED_ON|REPLICATED_TO]->(c2:Compute_Node)-[:GOVERNED_BY]->(b2:Compliance_Boundary)
            WHERE c1 <> c2 AND b1 <> b2
            RETURN count(DISTINCT d) AS n
            """
        ).single()["n"]

        ungoverned = session.run(
            """
            MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c:Compute_Node)
            WHERE d.classification IN $sensitive
              AND NOT (c)-[:GOVERNED_BY]->(:Compliance_Boundary)
            RETURN count(DISTINCT d) AS n
            """,
            sensitive=_SENSITIVE,
        ).single()["n"]

        weak_enc = session.run(
            """
            MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c:Compute_Node)
            WHERE d.classification IN $sensitive
              AND c.encryption IN $weak
            RETURN count(DISTINCT d) AS n
            """,
            sensitive=_SENSITIVE, weak=_WEAK_ENCRYPTION,
        ).single()["n"]

    return _classify(leaks, ungoverned, weak_enc)


def security_status_for_assets(asset_names: list[str]) -> dict:
    """Traffic-light status scoped to the specific assets a query touched.

    Same RED/AMBER/GREEN logic as ``security_status()`` (via the shared
    ``_classify`` helper), but every scan is restricted to ``asset_names`` so the
    dashboard reflects THIS submission rather than the whole graph. This is what
    makes the light change from submission to submission.

    An empty list => GREEN with zero counts (nothing sensitive was investigated
    this turn).

    Returns ``{level, leaks, ungoverned_assets, weak_encryption_assets}``.
    """
    if not asset_names:
        return _classify(0, 0, 0)

    with get_driver().session() as session:
        leaks = session.run(
            """
            MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c1:Compute_Node)-[:GOVERNED_BY]->(b1:Compliance_Boundary)
            MATCH (d)-[:STORED_ON|REPLICATED_TO]->(c2:Compute_Node)-[:GOVERNED_BY]->(b2:Compliance_Boundary)
            WHERE c1 <> c2 AND b1 <> b2 AND d.name IN $assets
            RETURN count(DISTINCT d) AS n
            """,
            assets=asset_names,
        ).single()["n"]

        ungoverned = session.run(
            """
            MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c:Compute_Node)
            WHERE d.name IN $assets
              AND d.classification IN $sensitive
              AND NOT (c)-[:GOVERNED_BY]->(:Compliance_Boundary)
            RETURN count(DISTINCT d) AS n
            """,
            assets=asset_names, sensitive=_SENSITIVE,
        ).single()["n"]

        weak_enc = session.run(
            """
            MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c:Compute_Node)
            WHERE d.name IN $assets
              AND d.classification IN $sensitive
              AND c.encryption IN $weak
            RETURN count(DISTINCT d) AS n
            """,
            assets=asset_names, sensitive=_SENSITIVE, weak=_WEAK_ENCRYPTION,
        ).single()["n"]

    return _classify(leaks, ungoverned, weak_enc)


def assets_on_locations(location_names: list[str]) -> list[str]:
    """Return the names of all Data_Assets stored or replicated to the given node(s).

    Used to give the traffic light a meaningful scope on turns that investigate a
    *location* (blast-radius / compliance-boundary lookups) rather than a named
    asset — the co-located assets become the thing whose security posture the
    light reflects. Empty input => empty list.
    """
    if not location_names:
        return []
    with get_driver().session() as session:
        rows = session.run(
            """
            MATCH (d:Data_Asset)-[:STORED_ON|REPLICATED_TO]->(c:Compute_Node)
            WHERE c.name IN $locations
            RETURN DISTINCT d.name AS name
            """,
            locations=location_names,
        ).data()
    return [r["name"] for r in rows]


def graph_summary() -> dict:
    """Return a ``{label: count}`` map of the current graph (excludes baseline node)."""
    with get_driver().session() as session:
        rows = session.run(
            """
            MATCH (n)
            WHERE NOT $bl IN labels(n)
            RETURN labels(n)[0] AS label, count(*) AS c
            ORDER BY label
            """,
            bl=_BASELINE_LABEL,
        ).data()
    return {r["label"]: r["c"] for r in rows}