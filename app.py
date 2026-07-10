import streamlit as st
import uuid
import json
from dotenv import load_dotenv
from src.agent import run_trace
from src.llm import build_llm, active_provider
from src.telemetry import init_telemetry
from src.graph_admin import (
    reset_graph,
    is_graph_modified,
    security_status,
    security_status_for_assets,
    assets_on_locations,
)
from src.graph_view import render_graph_tab, load_base_graph

# Initialize observability
init_telemetry()

# 1. Load system environment variables (.env file)
load_dotenv()

# 2. Helper function to parse raw LLM output into a clean string
def clean_agent_response(raw_response):
    if not raw_response:
        return None
        
    # If it's already a clean string, check if it's stringified JSON
    if isinstance(raw_response, str):
        try:
            parsed = json.loads(raw_response)
            # Handle stringified list of dicts
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed[0].get("text", raw_response)
            # Handle stringified dict
            elif isinstance(parsed, dict):
                return parsed.get("text", raw_response)
        except json.JSONDecodeError:
            # It's just a normal string, return as-is
            return raw_response
            
    # If the backend returned a native list object
    if isinstance(raw_response, list) and len(raw_response) > 0:
        if isinstance(raw_response[0], dict):
            return raw_response[0].get("text", str(raw_response))
        return str(raw_response[0])
        
    # If the backend returned a native dict
    if isinstance(raw_response, dict):
        return raw_response.get("text", str(raw_response))
        
    return str(raw_response)

# 2b. Dashboard indicators (graph drift + security traffic light)
def render_graph_state(container):
    """Show whether the graph has drifted from the seeded baseline."""
    try:
        modified = is_graph_modified()
    except Exception as e:
        container.caption(f"Graph state unavailable: {e}")
        return
    if modified is None:
        container.info("◽ Baseline not set — click **Reset Graph** to establish it.")
    elif modified:
        container.warning("🟠 Graph **MODIFIED** — differs from seed")
    else:
        container.success("🟢 Graph **pristine** — matches seed")


def render_security_light(container, status=None):
    """Render the security traffic light for the LAST query's result.

    ``status`` is the dict captured from the last query (scoped to the asset(s)
    that query investigated, or the whole-graph scan when a full audit ran), or
    None when no query has been run yet in this session — in which case all lamps
    are shown OFF with no status text or counts.
    """
    palette = {"RED": "#e0245e", "AMBER": "#f5a623", "GREEN": "#17bf63"}
    caption = {
        "RED": "SECURITY ISSUE DETECTED",
        "AMBER": "CAUTION — POSSIBLE ISSUE",
        "GREEN": "ALL CLEAR",
    }
    level = status["level"] if status else None  # None => all lamps off

    def lamp(color, active):
        glow = f"box-shadow:0 0 12px 2px {color};" if active else ""
        return (
            f"<div style='width:26px;height:26px;border-radius:50%;"
            f"background:{color};opacity:{'1' if active else '0.15'};{glow}'></div>"
        )

    housing = (
        "<div style='display:flex;flex-direction:column;gap:7px;background:#111;"
        "padding:9px;border-radius:10px;'>"
        f"{lamp(palette['RED'], level == 'RED')}"
        f"{lamp(palette['AMBER'], level == 'AMBER')}"
        f"{lamp(palette['GREEN'], level == 'GREEN')}"
        "</div>"
    )

    if status is None:
        body = ""  # no query run yet: lamps off, no text/warnings
    else:
        body = (
            "<div>"
            f"<div style='font-weight:700;font-size:1.05rem;color:{palette[level]};'>{caption[level]}</div>"
            f"<div style='font-size:0.85rem;opacity:0.85;margin-top:3px;'>"
            f"Cross-boundary leaks: <b>{status['leaks']}</b> &nbsp;•&nbsp; "
            f"Ungoverned sensitive assets: <b>{status['ungoverned_assets']}</b> &nbsp;•&nbsp; "
            f"Weak-encryption sensitive assets: <b>{status['weak_encryption_assets']}</b>"
            "</div></div>"
        )

    html = (
        "<div style='display:flex;align-items:center;gap:16px;padding:12px 16px;"
        "border:1px solid rgba(128,128,128,0.35);border-radius:12px;max-width:660px;'>"
        f"{housing}{body}</div>"
    )
    container.markdown(html, unsafe_allow_html=True)


def compute_submission_status(details: dict):
    """Derive the traffic-light status for a single chat submission.

    * If the submission ran the whole-graph leak audit, the global
      ``security_status()`` IS the correct answer for that turn.
    * Otherwise, scope the status to the asset(s) the submission investigated —
      directly (named assets) and/or via any location it looked at, resolved to
      the assets co-located there. This keeps the light meaningful on
      location-only follow-ups (e.g. blast-radius questions) instead of going
      dark, and lets it change from submission to submission.
    * If nothing asset- or location-related was touched, return None (lamps off).
    """
    try:
        if details.get("full_scan"):
            return security_status()

        assets = list(details.get("touched_assets") or [])
        locations = details.get("touched_locations") or []
        if locations:
            assets.extend(assets_on_locations(locations))

        # De-duplicate while preserving order.
        assets = list(dict.fromkeys(assets))
        if assets:
            return security_status_for_assets(assets)
        return None
    except Exception:
        return None


def record_submission_scope(details: dict) -> None:
    """Persist which nodes the last query touched, for the graph tab to highlight.

    Stored in session_state so the (separate) knowledge-graph tab can read it on
    the automatic rerun — no manual refresh, no re-query of the graph.
    """
    st.session_state.last_scope = {
        "assets": list(details.get("touched_assets") or []),
        "locations": list(details.get("touched_locations") or []),
    }

# 3. Configure Streamlit Page Layout
st.set_page_config(page_title="Lucid Lineage: Forensic Workspace", layout="wide")

# 4. Securely maintain Session State across browser refreshes
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# 5. Initialize and Cache the Live Google Gemini Agent
@st.cache_resource
def load_live_agent():
    # Model configuration lives in src/llm.py (single source of truth).
    llm = build_llm()
    if llm is None:
        st.error(f"❌ No API key found for the '{active_provider()}' LLM provider. Check your .env file.")
    return llm

live_agent = load_live_agent()

# 6. Sidebar - Access Control Panel
st.sidebar.title("🛡️ Access Control")
st.sidebar.caption(f"Session ID: {st.session_state.session_id[:8]}...")

iam_role = st.sidebar.selectbox(
    "Assume IAM Role",
    ["Security_Analyst", "Compliance_Auditor", "System_Admin"]
)

clearance = st.sidebar.selectbox(
    "Clearance Boundary",
    ["SC_Cleared", "DV_Cleared", "Public"]
)

# Reset mechanism to wipe context memory and start fresh
if st.sidebar.button("Reset Session"):
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.chat_history = []
    st.session_state.pop("last_security", None)  # clear traffic light until next query
    st.session_state.pop("last_scope", None)     # clear graph highlight until next query
    st.rerun()

# --- Graph Controls ---
st.sidebar.divider()
st.sidebar.subheader("🗄️ Graph Controls")

if st.sidebar.button("♻️ Reset Graph to Seed",
                     help="Wipe the graph and re-seed it from data/init_graph.cypher"):
    with st.spinner("Re-seeding graph from init_graph.cypher..."):
        try:
            summary = reset_graph()
            # The reset also wipes graph memory, so start a fresh UI session too.
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.chat_history = []
            st.session_state.pop("last_security", None)  # traffic light off until next query
            st.session_state.pop("last_scope", None)     # graph highlight off until next query
            load_base_graph.clear()                      # drop cached graph so the tab re-queries the new seed
            if summary["errors"]:
                st.sidebar.warning(
                    f"Reset completed with {len(summary['errors'])} statement error(s)."
                )
            else:
                st.sidebar.success("Graph reset to initial seed state.")
        except Exception as e:
            st.sidebar.error(f"Reset failed: {e}")
    st.rerun()

# Live indicator: has the graph drifted from the seeded baseline?
graph_state_ph = st.sidebar.empty()
render_graph_state(graph_state_ph)

# 7. Main Workspace — two tabs: the forensic chat, and the live knowledge graph
st.title("Lucid Lineage: Forensic Workspace")
st.caption("Immutable Graph-Based Auditing Engine")

tab_chat, tab_graph = st.tabs(["🔎 Forensic Workspace", "🕸️ Knowledge Graph"])

with tab_chat:
    # Security traffic light — reflects the LAST query's result (off until a query runs)
    st.subheader("🚦 Security Status")
    security_ph = st.empty()
    render_security_light(security_ph, st.session_state.get("last_security"))

    st.divider()

    # Display initialization status if conversation hasn't started
    if not st.session_state.chat_history:
        st.info("🤖 Initializing secure session. Ready to trace data lineage.")

    # Render previous turns from the current UI session state
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # 8. Chat Ingestion and Backend Pipeline
    if prompt := st.chat_input("Trace the lineage..."):

        # Immediately render and save the user's input to the interface
        with st.chat_message("user"):
            st.write(prompt)
        st.session_state.chat_history.append({"role": "user", "content": prompt})

        # Process the pipeline with a loading indicator
        with st.spinner("Analyzing data lineage via graph memory..."):
            details = run_trace(
                session_id=st.session_state.session_id,
                query=prompt,
                clearance=clearance,
                iam_role=iam_role,
                agent_llm=live_agent,
                return_details=True,  # also surfaces which asset(s) this submission investigated
            )

            # ---> Apply the cleaning function before rendering <---
            final_response = clean_agent_response(details["answer"])

        # Render and save the live AI output if successfully returned
        if final_response:
            with st.chat_message("assistant"):
                st.write(final_response)
            st.session_state.chat_history.append({"role": "assistant", "content": final_response})
        else:
            st.error("Trace failed. Check your terminal logs for Neo4j or API exceptions.")

        # Capture the security posture and the touched subgraph as of THIS query,
        # then refresh the indicators. The graph tab picks up last_scope on this
        # same rerun — no manual refresh needed.
        st.session_state.last_security = compute_submission_status(details)
        record_submission_scope(details)
        render_security_light(security_ph, st.session_state.get("last_security"))
        render_graph_state(graph_state_ph)

with tab_graph:
    render_graph_tab()