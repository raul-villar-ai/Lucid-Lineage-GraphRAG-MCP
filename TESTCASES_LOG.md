# Lucid Lineage — Test Case Execution Log

**Run date:** 2026-07-10 (full 4-scenario run after the agent-reasoning-guard
fixes: classification-aware leak count + `resolve_location`; adds the TC4
context-drift regression test)
**Harness:** `eval/run_testcases.py` (each scenario's turns run on a shared Neo4j
session, exercising graph-memory continuity and — for TC4 — cross-turn context drift)

## Environment
| Component | Value |
|-----------|-------|
| LLM | OpenAI `gpt-4o-mini` (temperature 0, `max_retries=3`, `timeout=120s`) — `LLM_PROVIDER=openai` |
| Graph DB | Neo4j Aura (driver 6.2.0) — enriched seed (pristine before the run): 8 boundaries, 11 compute nodes, 13 data assets, 6 service accounts |
| Orchestration | LangChain 1.x `create_tool_calling_agent`, **7 tools** (adds `resolve_location`); `max_iterations=20`, `max_execution_time=120s` |
| Runtime | Python 3.14.6 |

## Result Summary

| Test Case | Turns | Verdict |
|-----------|:-----:|---------|
| **TC1** — Asset Lineage & Co-Location | ✅ primary (7.7s) · ✅ follow-up (3.3s) | **PASS (2/2)** |
| **TC2** — Macro Leak Auditing & Policy Mapping | ✅ primary (5.9s) · ✅ follow-up (9.7s) | **PASS (2/2)** |
| **TC3** — Upstream Dependency & Mutation | ✅ primary (11.4s) · ✅ follow-up (3.3s) | **PASS (2/2)** |
| **TC4** — Context-Drift Node Resolution *(new)* | ✅ primary (8.3s) · ✅ follow-up 1 (3.2s) · ✅ follow-up 2 (10.6s) | **PASS (3/3)** |

**All 9 turns passed.** TC4 is the new single-session regression test for the
context-drift failure found this iteration.

### Deterministic tool-level ground truth (independent of the LLM)
| Check | Result |
|-------|:------:|
| `audit_restricted_asset_leaks()` (unfiltered) | 4 assets / 6 paths |
| `audit_restricted_asset_leaks("Highly_Restricted")` | **2 assets / 3 paths** (`EU_Customer_PII_Master`, `Cardholder_Transaction_Vault`) |
| `resolve_location("APAC gateway")` / `("gateway")` | **`APAC_Edge_Gateway`** |
| `resolve_location("APAC")` | AMBIGUOUS → 3 candidates (no guess) |
| Whole-graph `security_status()` | RED — leaks 4, ungoverned 2, weak-encryption 4 |

---

## TC1 — Asset Lineage & Location Co-Location
- **Primary** (✅ 7.7s, 3 tools): traced `Supply_Chain_Manifest` (uk-prod-worker-01 /
  `UK_Sovereign_Boundary` → us-cold-storage-99 / `CCPA_US_Privacy`) and flagged the
  **SOVEREIGN BOUNDARY BREACH**. Correctly did **not** log (read-only — no explicit
  log request).
- **Follow-up** (✅ 3.3s, 1 tool): resolved "that destination location" to
  us-cold-storage-99 and identified `Legacy_Customer_Archive`.

## TC2 — Macro Leak Auditing & Policy Mapping
- **Primary** (✅ 5.9s, 1 tool): called `audit_restricted_asset_leaks` with
  `classification='Highly_Restricted'` and reported **"2 Highly_Restricted assets"**
  (`Cardholder_Transaction_Vault`, `EU_Customer_PII_Master`). This is the fix for the
  recurring row-vs-distinct miscount: the tool now states the distinct count and the
  agent reports it verbatim (previously mis-reported as "3").
- **Follow-up** (✅ 9.7s, 4 tools): returned the governing policy for the leak node.

## TC3 — Upstream Dependency & Mutation Verification
- **Primary** (✅ 11.4s, 6 tools): identified the upstream sources feeding
  `APAC_Edge_Gateway` — `US_HQ_Mainframe_Vault` and `APAC_Tokyo_Cloud_01`.
- **Follow-up** (✅ 3.3s, 1 tool): on explicit instruction, logged an `Audit_Finding`
  on `NextGen_Algorithm_SourceCode`, grounded in the SOX/Corporate_IP governance of its
  source node. **This mutates the graph** (adds one finding) — re-seed to reset.

## TC4 — Context-Drift Node Resolution *(new regression test)*
Reproduces the failure where "APAC gateway" was previously resolved to the wrong node
after prior turns anchored the session elsewhere. All three turns share one session.
- **Primary** (✅ 8.3s, 3 tools): traced `Cardholder_Transaction_Vault`, flagged the
  PCI↔APAC breach (anchors the session on `APAC_Singapore_Analytics`).
- **Follow-up 1** (✅ 3.2s, 1 tool): returned `APAC_Singapore_Analytics` →
  `APAC_Data_Sovereignty` / Regional_Data_Residency_Required (deepens that context).
- **Follow-up 2 — the trap** (✅ 10.6s, 6 tools): the **verbatim original failing
  question** ("...Which source components are responsible for that pipeline?"). The
  agent called `resolve_location('APAC gateway')` → **`APAC_Edge_Gateway`** (NOT
  `APAC_Singapore_Analytics`), listed the `REPLICATED_TO` feeders
  (`Global_Supply_Telemetry`, `APAC_Regional_Sales`), and traced them back to the
  responsible source components **`US_HQ_Mainframe_Vault`** and **`APAC_Tokyo_Cloud_01`**.
  Tool sequence: `resolve_location` → `get_assets_in_location(APAC_Edge_Gateway)` →
  `check_asset_lineage` ×4. Matched all three regression keys.

---

## Notes

**What this run validates.** The two agent-reasoning guards work end-to-end against the
live model, not just as unit checks:
- **Distinct-count fix (item 2).** TC2 primary passed `classification='Highly_Restricted'`
  and reported the tool's distinct count (2) directly — the Q3-style "3 assets" miscount
  did not recur.
- **Node-resolution fix (item 3).** TC4 follow-up 2 resolved an ambiguous "APAC gateway"
  to `APAC_Edge_Gateway` despite two prior turns anchored on `APAC_Singapore_Analytics`,
  and traced back to the correct source components — the original Q5 bug, now a passing
  regression test.

These are mitigations, not guarantees: the agent layer remains probabilistic (see README
"Known Limitations"). TC4 is the durable single-session guard against this class of drift.

**Graph state after run.** TC3's follow-up logged one `Audit_Finding` (expected — an
explicit-log turn). The graph was re-seeded to pristine after capturing these results.

**Reproduce:**
```
python seed_db.py                 # reset to pristine enriched seed
python eval/run_testcases.py      # runs TC1–TC4, writes eval/_results.json
```
Set `LLM_PROVIDER` in `.env` (`openai` or `google`) to pick the backend.
