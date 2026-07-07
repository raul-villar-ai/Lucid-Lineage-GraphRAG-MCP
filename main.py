import sys
import uuid

from src.agent import run_trace
from src.llm import build_llm
from src.telemetry import init_telemetry

# Windows consoles default to a legacy code page (cp1252) which cannot encode the
# bullet points / unicode the agent emits, raising UnicodeEncodeError mid-print.
# Force UTF-8 on the standard streams when the interpreter supports it.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main():
    init_telemetry()
    print("--- Initializing Lucid Lineage Forensic Terminal ---")
    print("[IAM Check]: Simulated SC Clearance Verified. Access Granted.")

    # Generate a persistent session ID for this terminal instance
    session_id = str(uuid.uuid4())
    print(f"[Context Graph]: Session {session_id} Initialized.\n")

    iam_role = "Security_Analyst"
    clearance = "SC_Cleared"

    # Build the live Gemini agent. If no API key is configured, run_trace falls
    # back to mock mode automatically (agent_llm=None).
    agent_llm = build_llm()
    if agent_llm is None:
        print("[WARN] GOOGLE_API_KEY not set — running in MOCK mode (no live reasoning).\n")

    while True:
        query = input("\nAudit Query (or 'exit' to quit) > ")
        if query.lower() in ['exit', 'quit']:
            break

        print("Tracing lineage and querying graph memory...\n")

        # The agent will automatically write to and read from Neo4j Context Memory
        response = run_trace(
            session_id=session_id,
            query=query,
            iam_role=iam_role,
            clearance=clearance,
            agent_llm=agent_llm,
        )

        print(f"\n[Lucid Engine]:\n{response}")


if __name__ == "__main__":
    main()
