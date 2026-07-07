# Lucid Lineage — Test Case Execution Log

**Run date:** 2026-07-07 (re-run against the **enriched** graph)
**Harness:** `eval/run_testcases.py` (each scenario's primary + follow-up run on a
shared Neo4j session, exercising graph-memory continuity)

## Environment
| Component | Value |
|-----------|-------|
| LLM | Google `gemini-3.5-flash` (temperature 0, `max_retries=3`, `timeout=120s`) |
| Graph DB | Neo4j Aura (driver 6.2.0) — **enriched seed**: 8 boundaries, 11 compute nodes, 13 data assets, 6 service accounts |
| Orchestration | LangChain 1.x `create_tool_calling_agent`; `max_iterations=20`, `max_execution_time=120s` |
| Runtime | Python 3.14.6 (`-X utf8`) |

## Result Summary

| Test Case | Primary | Follow-up | Verdict |
|-----------|:-------:|:---------:|---------|
| **TC1** — Asset Lineage & Co-Location | ✅ PASS | ✅ PASS | **PASS (2/2)** |
| **TC2** — Macro Leak Auditing & Policy Mapping | ✅ PASS | ⚠️ transient API disconnect | **PARTIAL (1/2)** |
| **TC3** — Upstream Dependency & Mutation | ✅ PASS | ⚠️ transient API disconnect | **PARTIAL (1/2)** |

**All three primary audits pass with correct, richer results.** The two follow-up
failures are the recurring upstream Gemini `Server disconnected` error (see notes) —
not a code or data defect.

### Deterministic tool-level validation — 100% PASS
Independent of the LLM, every tool query the scenarios rely on returns the expected
data against the enriched graph (this is the durable guarantee that the graph
"always" supports the tests):

| Check | Result |
|-------|:------:|
| TC1 `check_asset_lineage(Supply_Chain_Manifest)` → UK + US nodes + boundaries | ✅ |
| TC1 `get_assets_in_location(us-cold-storage-99)` → Legacy_Customer_Archive | ✅ |
| TC2 `audit_restricted_asset_leaks()` → EU_Customer_PII_Master **and** Cardholder_Transaction_Vault | ✅ |
| TC3 `get_assets_in_location(APAC_Edge_Gateway)` → 4 assets (2 upstream, 2 local) | ✅ |
| TC3 `check_asset_lineage(Global_Supply_Telemetry)` → US_HQ_Mainframe_Vault → APAC | ✅ |

---

## TC1 — Asset Lineage & Location Co-Location
- **Primary** (✅ PASS, 12.6s): Traced `Supply_Chain_Manifest` (uk-prod-worker-01 /
  `UK_Sovereign_Boundary` → us-cold-storage-99 / `CCPA_US_Privacy`), flagged the
  **SOVEREIGN BOUNDARY BREACH**, logged a finding.
- **Follow-up** (✅ PASS, 5.7s): Correctly resolved "that destination location" to
  `us-cold-storage-99` from prior context and identified `Legacy_Customer_Archive`.
  Graph-memory continuity verified.

## TC2 — Macro Leak Auditing & Policy Mapping
- **Primary** (✅ PASS, 16.9s): Correctly identified **both** geographical leaks of
  Highly_Restricted assets — `EU_Customer_PII_Master` (GDPR→CCPA) and the newly
  seeded `Cardholder_Transaction_Vault` (PCI→APAC) — and correctly classified
  `NextGen_Algorithm_SourceCode` as a *non-geographical* (local, dual-regulation)
  boundary crossing. Findings logged.
- **Follow-up** (⚠️ FAIL, transient): `Agent invocation failed: Server disconnected
  without sending a response.` Gracefully caught by `run_trace`.

## TC3 — Upstream Dependency & Mutation Verification
- **Primary** (✅ PASS, 24.4s): Now **unambiguous** thanks to the enrichment —
  identified both upstream source components feeding `APAC_Edge_Gateway`
  (`US_HQ_Mainframe_Vault` via `NextGen_Algorithm_SourceCode` + `Global_Supply_Telemetry`,
  and `APAC_Tokyo_Cloud_01` via `APAC_Regional_Sales`) and correctly noted
  `APAC_IoT_Telemetry_Logs` is generated locally.
- **Follow-up** (⚠️ FAIL, transient): same `Server disconnected` upstream error.

---

## Notes

**Graph enrichment (this iteration).** `data/init_graph.cypher` gained an additive
Section 9: 3 new compliance boundaries, 4 compute nodes, 5 data assets, 2 service
accounts. It makes TC3's "upstream into APAC" explicit (modeled `US_HQ`/`Tokyo →
APAC_Edge_Gateway` pipelines), adds a clean second cross-boundary leak (PCI→APAC),
and broadens the topology for future tests. Sections 1–8 are untouched, so TC1/TC2
behaviour is preserved. Enrichment validated end-to-end (see deterministic table).

**Follow-up failures are environmental, not code/data.** Evidence:
- All 3 primaries pass consistently across 3 harness runs.
- Follow-ups fail with `Server disconnected` at **varying** times (60s / 60.5s /
  101.9s) — inconsistent with any fixed client cap (client `timeout=120s`).
- A pristine-graph re-run (clearing accumulated audit findings) did **not** change
  the outcome, ruling out context bloat.
- The follow-ups' required capabilities (`check_compliance_boundary`,
  `log_audit_finding`) succeed in the primaries and in the 100%-passing deterministic
  suite; TC3's follow-up (audit write) passed in an earlier stable-API run.
- Mitigations already in place: `max_retries=3`, request `timeout=120s`, a graceful
  `max_execution_time` cap, and try/except that returns a clean error string.

**Reproduce:** `python eval/run_testcases.py` (writes `eval/_results.json`).
**Reset graph to pristine seed:** `python seed_db.py` **or** the "♻️ Reset Graph to
Seed" button in the Streamlit sidebar.
