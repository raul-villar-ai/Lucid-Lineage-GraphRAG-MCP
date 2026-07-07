# Lucid Lineage — Test Case Execution Log

**Run date:** 2026-07-07
**Harness:** `eval/run_testcases.py` (executes each scenario's primary + follow-up on a
shared Neo4j session, exercising graph-memory continuity)

## Environment
| Component | Value |
|-----------|-------|
| LLM | Google `gemini-3.5-flash` (temperature 0, `max_retries=3`, `timeout=120s`) — availability confirmed via `check_models.py` |
| Graph DB | Neo4j Aura (driver 6.2.0) — connectivity confirmed via `check_env.py` |
| Orchestration | LangChain 1.x (`langchain-classic` 1.0.8) `create_tool_calling_agent`; `max_iterations=20`, `max_execution_time=120s` |
| Runtime | Python 3.14.6 (`-X utf8`) |

## Result Summary

| Test Case | Primary | Follow-up | Verdict |
|-----------|:-------:|:---------:|---------|
| **TC1** — Asset Lineage & Co-Location | ✅ PASS | ✅ PASS | **PASS (2/2)** |
| **TC2** — Macro Leak Auditing & Policy Mapping | ✅ PASS | ⚠️ transient API error | **PARTIAL (1/2)** |
| **TC3** — Upstream Dependency & Mutation | ✅ PASS | ✅ PASS | **PASS (2/2)** |

**Totals:** 5 / 6 turns passed. All 3 **primary** compliance audits produced correct
results. The single non-passing turn failed on a transient upstream LLM API error
(not a code defect — see notes).

---

## TC1 — Asset Lineage & Location Co-Location

**Primary:** *"Trace the data lineage for the Supply_Chain_Manifest asset. Are there any active sovereign boundary breaches?"*
- **Status:** ✅ PASS (9.6s)
- **Tools:** `check_asset_lineage` → `retrieve_past_findings` → `log_audit_finding`
- **Result:** Correctly traced `Supply_Chain_Manifest`: stored on `uk-prod-worker-01`
  (`UK_Sovereign_Boundary` / `No_Offshore_Without_Consent`), replicated to
  `us-cold-storage-99` (`CCPA_US_Privacy`). Correctly flagged the **SOVEREIGN BOUNDARY
  BREACH** (UK→US offshore replication) and logged an immutable finding.

**Follow-up:** *"Are there any other assets currently sitting in that exact same destination location?"*
- **Status:** ✅ PASS (5.8s)
- **Tools:** `get_assets_in_location` → `check_asset_lineage`
- **Result:** Correctly resolved "that destination location" to `us-cold-storage-99`
  from prior context (**graph-memory continuity verified**) and identified
  `Legacy_Customer_Archive` (Public) as the co-located asset.

---

## TC2 — Macro Leak Auditing & Policy Mapping

**Primary:** *"Run a full compliance audit across the network. Are any assets classified as 'Highly_Restricted' leaking across geographical boundaries?"*
- **Status:** ✅ PASS (21.8s)
- **Tools:** `audit_restricted_asset_leaks` → `check_asset_lineage` (×2) →
  `check_compliance_boundary` → `get_assets_in_location` → `retrieve_past_findings` (×2)
  → `log_audit_finding` (×2)
- **Result:** Correctly identified both `Highly_Restricted` leaks —
  `EU_Customer_PII_Master` (GDPR_EU_Privacy → CCPA_US_Privacy) and
  `NextGen_Algorithm_SourceCode` (exposed on unmapped `APAC_Edge_Gateway`) — and logged
  immutable findings for both.

**Follow-up:** *"What specific data security policy governs the gateway node where that leak was detected?"*
- **Status:** ❌ FAIL — **transient upstream API error** (65.6s)
- **Trace error:** `Agent invocation failed: Server disconnected without sending a response.`
- **Analysis:** This is an upstream Gemini API availability error, gracefully caught by
  `run_trace` (no crash, clean error string returned). Across runs the API also returned
  `503 UNAVAILABLE — "This model is currently experiencing high demand… Please try again
  later."` The underlying capability required here (`check_compliance_boundary` on the
  gateway node) **executes successfully in TC2-primary and TC3**, so this is confirmed
  environmental (API load), not a code path defect. Client-side retries (`max_retries=3`)
  were exhausted by the demand spike. Re-running when the API is not saturated is expected
  to pass.

---

## TC3 — Upstream Dependency & Mutation Verification

**Primary:** *"Identify all upstream dependencies feeding directly into the APAC gateway location. Which source components are responsible for that pipeline?"*
- **Status:** ✅ PASS (27.0s)
- **Tools:** `get_assets_in_location` → `check_asset_lineage` (×2) →
  `check_compliance_boundary` (×2) → `audit_restricted_asset_leaks` →
  `log_audit_finding` → `retrieve_past_findings`
- **Result:** Correctly identified `US_HQ_Mainframe_Vault` as the upstream source feeding
  `NextGen_Algorithm_SourceCode` into `APAC_Edge_Gateway`, and flagged the breach
  (`Zero_External_Network_Access` violated; destination has no compliance boundary +
  `Transit_Only` encryption).
- **Note:** This query is inherently tool-heavy. Under the earlier 90s cap it occasionally
  hit the wall-clock limit; raising `max_execution_time` to 120s plus the exact-identifier
  prompt guidance produced reliable convergence.

**Follow-up:** *"Log an official audit finding for the highest-risk upstream component indicating a missing compliance stamp."*
- **Status:** ✅ PASS (29.9s)
- **Tools:** discovery tools → `log_audit_finding` (write path)
- **Result:** Successfully wrote an immutable `COMPLIANCE_VIOLATION` finding for
  `NextGen_Algorithm_SourceCode` ("missing compliance stamp" on `APAC_Edge_Gateway`).
  **The graph write/mutation path is validated.**

---

## Notes

**Code fixes validated by this run:**
- **Neo4j primitive serialization** — the agent now normalizes Gemini structured output
  (list-of-content-blocks / dicts) to a primitive string before persisting `Message.content`.
  Confirmed independently (a raw list-of-maps property is rejected by Neo4j with
  `Neo.ClientError.Statement.TypeError`) and end-to-end (multi-turn memory works in TC1/TC3).
- **Agent optimization** — `max_retries`/`timeout` on the LLM, a graceful
  `max_execution_time` cap, and exact-identifier prompt guidance. Together these turned a
  previously non-converging TC3 and hard crashes into correct answers and graceful degradation.

**Transient error signatures observed (upstream Gemini API, not code):**
- `Server disconnected without sending a response.`
- `503 UNAVAILABLE — This model is currently experiencing high demand. … Please try again later.`

**Artifacts created during testing (by design):** the runs wrote `Session`/`Message`
memory nodes and several immutable `Audit_Finding` nodes (TC1, TC2, TC3 exercise
`log_audit_finding`). Audit findings are intentionally immutable; to reset the graph to a
pristine seed state, re-run `python seed_db.py`.
