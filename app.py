import streamlit as st
import uuid
import json
from dotenv import load_dotenv
from src.agent import run_trace
from src.llm import build_llm
from src.telemetry import init_telemetry

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
        st.error("❌ GOOGLE_API_KEY is missing from your .env file!")
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
    st.rerun()

# 7. Main Workspace Layout UI
st.title("Lucid Lineage: Forensic Workspace")
st.caption("Immutable Graph-Based Auditing Engine")
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
        raw_response = run_trace(
            session_id=st.session_state.session_id,
            query=prompt,
            clearance=clearance,
            iam_role=iam_role,
            agent_llm=live_agent
        )
        
        # ---> Apply the cleaning function before rendering <---
        final_response = clean_agent_response(raw_response)
    
    # Render and save the live AI output if successfully returned
    if final_response:
        with st.chat_message("assistant"):
            st.write(final_response)
        st.session_state.chat_history.append({"role": "assistant", "content": final_response})
    else:
        st.error("Trace failed. Check your terminal logs for Neo4j or API exceptions.")