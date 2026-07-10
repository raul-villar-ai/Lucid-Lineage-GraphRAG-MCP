"""
Lucid Lineage — Knowledge Graph View (dedicated Streamlit tab).

Renders the enterprise knowledge graph using st-link-analysis (a Cytoscape.js
Streamlit component). Design goals, in order of the constraints that drove them:

  * No database churn — the base graph is queried from Neo4j ONCE and cached
    with ``@st.cache_data``. Each chat submission only recomputes which nodes are
    *highlighted* (cheap, pure-Python), never re-queries the graph.

  * No reload / no flicker — st-link-analysis is a keyed Streamlit component, so
    on Streamlit's automatic rerun (which happens on every chat submit) it
    reconciles in place with the new highlight state rather than reloading an
    iframe. Contrast with a raw ``components.html`` embed, which reloads and
    re-runs its layout on every rerun.

  * No manual refresh — the tab reads the last query's scope from
    ``st.session_state['last_scope']`` (written by app.py after each trace) and
    re-renders automatically. The user just switches tabs and it is current.

Node ``id`` == entity name (names are unique in this graph), which lets us map
the agent's ``touched_assets`` / ``touched_locations`` straight onto node ids.
"""

import logging
import streamlit as st

from src.db import get_driver

log = logging.getLogger("lucid_lineage.graph_view")

# Core infrastructure only — chat-memory (Session/Message), Audit_Finding, and the
# internal _GraphBaseline node are excluded to keep the view legible.
_NODE_LABELS = ["Data_Asset", "Compute_Node", "Compliance_Boundary", "Service_Account"]
_EDGE_TYPES = ["STORED_ON", "REPLICATED_TO", "GOVERNED_BY", "HAS_ACCESS"]

# Vivid palette per node type (active); one muted tone for dimmed / out-of-scope.
_TYPE_COLOR = {
    "Data_Asset": "#38bdf8",         # sky
    "Compute_Node": "#a78bfa",       # violet
    "Compliance_Boundary": "#f59e0b",# amber
    "Service_Account": "#34d399",    # green
}
_DIM_COLOR = "#3a3f4b"               # slate grey

# Deterministic layouts keep node positions identical between questions (no
# jumping); 'cose' is the most organic-looking but is force-directed and may
# re-settle when the highlight changes.
_LAYOUTS = ["cose", "concentric", "breadthfirst", "circle", "grid"]


@st.cache_data(show_spinner=False)
def load_base_graph() -> dict:
    """Query the core infrastructure graph from Neo4j ONCE and cache it.

    Returns a Cytoscape-style elements dict ``{"nodes": [...], "edges": [...]}``.
    Call ``load_base_graph.clear()`` after a graph reset to force a re-query.
    """
    nodes, edges = [], []
    with get_driver().session() as session:
        node_rows = session.run(
            """
            MATCH (n)
            WHERE any(l IN labels(n) WHERE l IN $labels)
            RETURN n.name AS name, [l IN labels(n) WHERE l IN $labels][0] AS ntype
            """,
            labels=_NODE_LABELS,
        ).data()
        edge_rows = session.run(
            """
            MATCH (a)-[r]->(b)
            WHERE type(r) IN $types
              AND any(l IN labels(a) WHERE l IN $labels)
              AND any(l IN labels(b) WHERE l IN $labels)
            RETURN a.name AS source, type(r) AS rel, b.name AS target
            """,
            types=_EDGE_TYPES, labels=_NODE_LABELS,
        ).data()

    for r in node_rows:
        if r["name"] is None:
            continue
        nodes.append({"data": {"id": r["name"], "name": r["name"], "ntype": r["ntype"]}})
    for r in edge_rows:
        edges.append({"data": {
            "id": f"{r['source']}|{r['rel']}|{r['target']}",
            "label": r["rel"],
            "source": r["source"],
            "target": r["target"],
        }})
    return {"nodes": nodes, "edges": edges}


def _active_set(elements: dict, touched: set[str]) -> set[str]:
    """Touched nodes plus their one-hop neighbours — the 'affected subgraph'.

    If nothing has been touched yet, treat every node as active so the initial
    view shows the whole estate in colour rather than greyed out.
    """
    all_ids = {n["data"]["id"] for n in elements["nodes"]}
    if not touched:
        return all_ids
    active = {t for t in touched if t in all_ids}
    for e in elements["edges"]:
        s, t = e["data"]["source"], e["data"]["target"]
        if s in active or t in active:
            active.add(s)
            active.add(t)
    return active


def _styled_elements(elements: dict, active: set[str]) -> dict:
    """Assign each node a style group: ``<Type>`` if active else ``<Type>_dim``.

    Highlighting is done purely by swapping the node's style group, so node ids
    (and therefore layout positions) stay stable across questions.
    """
    styled_nodes = []
    for n in elements["nodes"]:
        d = dict(n["data"])
        ntype = d.get("ntype", "Data_Asset")
        d["label"] = ntype if d["id"] in active else f"{ntype}_dim"
        styled_nodes.append({"data": d})
    return {"nodes": styled_nodes, "edges": elements["edges"]}


def _node_styles():
    from st_link_analysis import NodeStyle
    # NodeStyle(group_label, color, caption_field). One vivid + one dim per type.
    styles = []
    for ntype, color in _TYPE_COLOR.items():
        styles.append(NodeStyle(ntype, color, "name"))
        styles.append(NodeStyle(f"{ntype}_dim", _DIM_COLOR, "name"))
    return styles


def _edge_styles():
    from st_link_analysis import EdgeStyle
    # EdgeStyle(group_label, caption_field, directed). Caption shows the rel type.
    return [EdgeStyle(rel, caption="label", directed=True) for rel in _EDGE_TYPES]


def render_graph_tab() -> None:
    """Render the knowledge-graph tab, highlighting the last query's subgraph."""
    try:
        from st_link_analysis import st_link_analysis
    except ImportError:
        st.error(
            "The graph view needs the `st-link-analysis` package. Install it with "
            "`pip install st-link-analysis` (it is included in requirements.txt)."
        )
        return

    try:
        base = load_base_graph()
    except Exception as e:
        st.error(f"Could not load the graph from Neo4j: {e}")
        return

    if not base["nodes"]:
        st.info("The graph is empty. Use **Reset Graph to Seed** in the sidebar first.")
        return

    scope = st.session_state.get("last_scope") or {}
    touched = set(scope.get("assets", [])) | set(scope.get("locations", []))

    if touched:
        st.caption(
            "Highlighting the subgraph touched by the last query "
            f"({len(touched)} node(s) in focus): {', '.join(sorted(touched))}."
        )
    else:
        st.caption(
            "Showing the full infrastructure graph. Ask a question in the "
            "Forensic Workspace tab and the affected nodes light up here."
        )

    layout = st.selectbox(
        "Layout", _LAYOUTS, index=0,
        help="Deterministic layouts (concentric / breadthfirst / circle / grid) "
             "keep node positions stable between questions; 'cose' looks the most "
             "organic but may re-settle when the highlight changes.",
        key="graph_layout_choice",
    )

    active = _active_set(base, touched)
    elements = _styled_elements(base, active)

    # A STABLE key is what makes the component reconcile in place across reruns
    # (updating highlight) instead of reloading an iframe.
    st_link_analysis(
        elements,
        layout,
        _node_styles(),
        _edge_styles(),
        key="lucid_knowledge_graph",
    )