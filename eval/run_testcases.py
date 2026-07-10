"""
Lucid Lineage — Automated Test Harness.

Executes the scenarios defined in TESTCASES.md against the live agent pipeline.
Each test case runs its primary + follow-up query on a SHARED session id, so the
run also exercises Neo4j graph-memory continuity (the follow-up depends on context
from the primary turn).

Results are written to `eval/_results.json` for downstream reporting
(TESTCASES_LOG.md). Run from the repository root:

    python eval/run_testcases.py
"""

import io
import json
import os
import sys
import time
import uuid
import traceback
from contextlib import redirect_stdout

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure the repository root is importable regardless of the invocation cwd
# (running `python eval/run_testcases.py` puts eval/ on sys.path, not the root).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.agent import run_trace
from src.llm import build_llm, active_provider

TESTCASES = [
    {
        "id": 1,
        "title": "Asset Lineage & Location Co-Location",
        "turns": [
            {"q": "Trace the data lineage for the Supply_Chain_Manifest asset. "
                  "Are there any active sovereign boundary breaches?",
             "expect": ["Supply_Chain_Manifest", "boundary", "breach"]},
            {"q": "Are there any other assets currently sitting in that exact same "
                  "destination location?",
             "expect": ["Legacy_Customer_Archive"]},
        ],
    },
    {
        "id": 2,
        "title": "Macro Leak Auditing & Policy Mapping",
        "turns": [
            {"q": "Run a full compliance audit across the network. Are any assets "
                  "classified as 'Highly_Restricted' leaking across geographical boundaries?",
             "expect": ["EU_Customer_PII_Master", "leak"]},
            {"q": "What specific data security policy governs the gateway node where "
                  "that leak was detected?",
             "expect": ["policy"]},
        ],
    },
    {
        "id": 3,
        "title": "Upstream Dependency & Mutation Verification",
        "turns": [
            {"q": "Identify all upstream dependencies feeding directly into the APAC "
                  "gateway location. Which source components are responsible for that pipeline?",
             "expect": ["APAC"]},
            {"q": "Log an official audit finding for the highest-risk upstream component "
                  "indicating a missing compliance stamp.",
             "expect": ["finding"]},
        ],
    },
]


def _matched(text, keys):
    t = (text or "").lower()
    return [k for k in keys if k.lower() in t]


def main():
    llm = build_llm()
    mode = "LIVE" if llm is not None else "MOCK"
    # Reflect the actual active provider (src.llm toggle) rather than a hardcoded name.
    print(f"=== Lucid Lineage Test Harness ({mode}, provider={active_provider()}) ===")

    results = []
    for tc in TESTCASES:
        sid = str(uuid.uuid4())
        tc_rec = {"id": tc["id"], "title": tc["title"], "session_id": sid, "turns": []}
        for i, turn in enumerate(tc["turns"]):
            kind = "primary" if i == 0 else "follow-up"
            buf = io.StringIO()
            err = None
            t0 = time.perf_counter()
            try:
                with redirect_stdout(buf):
                    resp = run_trace(
                        session_id=sid,
                        query=turn["q"],
                        clearance="SC_Cleared",
                        iam_role="Compliance_Auditor",
                        agent_llm=llm,
                    )
            except Exception:
                resp = None
                err = traceback.format_exc()
            elapsed = round(time.perf_counter() - t0, 2)

            resp_text = resp if isinstance(resp, str) else json.dumps(resp, default=str)
            is_error = bool(err) or (isinstance(resp_text, str) and (
                resp_text.startswith("Agent invocation failed")
                or "Database query failed" in resp_text
                or "Database write failed" in resp_text))

            verbose = buf.getvalue()
            tools_called = [ln.strip() for ln in verbose.splitlines() if "Invoking:" in ln]

            tc_rec["turns"].append({
                "kind": kind,
                "query": turn["q"],
                "elapsed_s": elapsed,
                "resp_type": type(resp).__name__,
                "response": resp_text,
                "error": err,
                "expect": turn["expect"],
                "matched": _matched(resp_text, turn["expect"]),
                "is_error": is_error,
                "tools_called": tools_called,
            })

            status = "ERROR" if is_error else "OK"
            print(f"[TC{tc['id']} {kind:9}] {status:5} {elapsed:6.2f}s "
                  f"type={type(resp).__name__} tools={len(tools_called)} "
                  f"matched={_matched(resp_text, turn['expect'])}")
        results.append(tc_rec)

    with open("eval/_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("=== results written to eval/_results.json ===")


if __name__ == "__main__":
    main()
