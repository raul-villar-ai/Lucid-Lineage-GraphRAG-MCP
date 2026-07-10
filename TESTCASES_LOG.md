# Lucid Lineage — Test Case Execution Log

**Run date:** 2026-07-10 (regenerated from a live run after the cross-boundary
leak-guard fix; supersedes the 2026-07-07 Gemini run)
**Harness:** `eval/run_testcases.py` (each scenario's primary + follow-up run on a
shared Neo4j session, exercising graph-memory continuity)

> **Why this log was regenerated.** The previous log predated the leak-guard fix
> (`c1 <> c2` / canonical `c1.name < c2.name`) and described
> `NextGen_Algorithm_SourceCode` as a reported "non-geographical boundary crossing."
> That was exactly the **false positive the fix removed** — a single node
> (`US_HQ_Mainframe_Vault`) governed by two boundaries is no longer mis-reported as a
> leak. This log replaces that stale narrative with what the live run actually
> returns, and corrects the leak count.

## Environment
| Component | Value |
|-----------|-------|
| LLM | **OpenAI `gpt-4o-mini`** (temperature 0, `max_retries=3`, `timeout=120s`) — `LLM_PROVIDER=openai`. *(Previous run used Google `gemini-3.5-flash`; the provider is a `.env` toggle, `src/llm.py`.)* |
| Graph DB | Neo4j Aura (driver 6.2.0) — **enriched seed** (pristine, re-seeded before the run): 8 boundaries, 11 compute nodes, 13 data assets, 6 service accounts |
| Orchestration | LangChain 1.x `create_tool_calling_agent` (`langchain_core` 1.4.8); `max_iterations=20`, `max_execution_time=120s` |
| Runtime | Python 3.14.6 |

## Result Summary

| Test Case | Primary | Follow-up | Verdict |
|-----------|:-------:|:---------:|---------|
| **TC1** — Asset Lineage & Co-Location | ✅ PASS (8.24s) | ✅ PASS (4.33s) | **PASS (2/2)** |
| **TC2** — Macro Leak Auditing & Policy Mapping | ✅ PASS (5.01s) | ✅ PASS (3.19s) | **PASS (2/2)** |
| **TC3** — Upstream Dependency & Mutation | ✅ PASS (11.58s) | ✅ PASS (4.21s) | **PASS (2/2)** |

**All six turns passed (6/6).** Unlike the prior Gemini run, there were **no
transient upstream disconnects** this time; every primary and every follow-up
returned a correct, grounded answer.

### Deterministic tool-level validation — 100% PASS
Captured directly against the pristine seed **before** the LLM run (independent of
the model), so these are the durable ground truth:

| Check | Result |
|-------|:------:|
| `audit_restricted_asset_leaks()` → **4 distinct leaking assets / 6 boundary-crossing paths** | ✅ |
| &nbsp;&nbsp;• Highly_Restricted (geographical): `EU_Customer_PII_Master` (GDPR↔CCPA, 2 paths), `Cardholder_Transaction_Vault` (APAC↔PCI, 1 path) | ✅ |
| &nbsp;&nbsp;• Restricted: `Q3_Global_Financial_Ledger` (GDPR↔SOX/Corporate_IP, 2 paths), `Supply_Chain_Manifest` (UK↔CCPA, 1 path) | ✅ |
| &nbsp;&nbsp;• `NextGen_Algorithm_SourceCode` is **NOT** reported (was the removed self-node false positive) | ✅ |
| Whole-graph `security_status()` → `RED` — leaks **4**, ungoverned sensitive **2**, weak-encryption sensitive **4** | ✅ |
| TC1 `check_asset_lineage(Supply_Chain_Manifest)` → uk-prod-worker-01 (`UK_Sovereign_Boundary`) + us-cold-storage-99 (`CCPA_US_Privacy`) | ✅ |
| TC1 `get_assets_in_location(us-cold-storage-99)` → `Supply_Chain_Manifest`, `Legacy_Customer_Archive` | ✅ |
| TC3 `get_assets_in_location(APAC_Edge_Gateway)` → 4 assets (2 upstream-replicated, 2 local) | ✅ |

**Corrected leak count for TC2.** The full-graph scan now reports **4** distinct
leaking assets / **6** paths. The question TC2 actually asks — *Highly_Restricted*
assets leaking across *geographical* boundaries — is answered by exactly **2** of
them: `EU_Customer_PII_Master` and `Cardholder_Transaction_Vault`. The prior log's
value of "2" was the correct answer to that narrower question, but it (a) omitted the
two Restricted-class leaks the raw tool also returns, and (b) credited the agent with
flagging `NextGen_Algorithm_SourceCode`, which the fixed scan no longer surfaces.

---

## TC1 — Asset Lineage & Location Co-Location
- **Primary** (✅ PASS, 8.24s, 1 tool): `check_asset_lineage(Supply_Chain_Manifest)`.
  Traced uk-prod-worker-01 / `UK_Sovereign_Boundary` (No_Offshore_Without_Consent) →
  us-cold-storage-99 / `CCPA_US_Privacy` (Standard_Privacy_Controls) and explicitly
  flagged the **SOVEREIGN BOUNDARY BREACH**. Correctly did **not** log a finding
  (read-only discipline held — the prompt only asked to trace/identify).
- **Follow-up** (✅ PASS, 4.33s, 1 tool): `get_assets_in_location(us-cold-storage-99)`.
  Resolved "that exact same destination location" to `us-cold-storage-99` from prior
  context and identified `Legacy_Customer_Archive` (Public) alongside the manifest.
  Graph-memory continuity verified.

## TC2 — Macro Leak Auditing & Policy Mapping
- **Primary** (✅ PASS, 5.01s, 1 tool): `audit_restricted_asset_leaks()`. Correctly
  scoped its answer to the **Highly_Restricted** class the user asked about, reporting
  `Cardholder_Transaction_Vault` (APAC_Singapore_Analytics `APAC_Data_Sovereignty` ↔
  US_Payments_Processor `PCI_DSS_Payments`) and `EU_Customer_PII_Master`
  (EU_Frankfurt_Cloud_01 / EU_Paris_DR_Cluster `GDPR_EU_Privacy` ↔ US_East_Analytics_Pool
  `CCPA_US_Privacy`). It did **not** report the Restricted-class leaks
  (`Q3_Global_Financial_Ledger`, `Supply_Chain_Manifest`) and did **not** mis-report
  `NextGen_Algorithm_SourceCode` — the exact behaviour the leak-guard fix intends.
- **Follow-up** (✅ PASS, 3.19s, 1 tool): `check_compliance_boundary(US_East_Analytics_Pool)`.
  Resolved "the node where that leak was detected" to the `EU_Customer_PII_Master`
  destination node and returned its governing policy: `CCPA_US_Privacy` /
  Standard_Privacy_Controls / tier Elevated. Data matches the seed.

## TC3 — Upstream Dependency & Mutation Verification
- **Primary** (✅ PASS, 11.58s, 5 tools): `get_assets_in_location(APAC_Edge_Gateway)`
  then `check_asset_lineage` on each co-located asset. Identified the true upstream
  sources feeding the APAC gateway — `US_HQ_Mainframe_Vault` (via
  `NextGen_Algorithm_SourceCode` and `Global_Supply_Telemetry`) and
  `APAC_Tokyo_Cloud_01` (via `APAC_Regional_Sales`) — and noted `APAC_IoT_Telemetry_Logs`
  as locally originated. (Wording note: the model lists the locally-stored assets under
  the same heading as the replicated-in pipelines; the identified source *locations* are
  correct.)
- **Follow-up** (✅ PASS, 4.21s, 1 tool): `log_audit_finding(NextGen_Algorithm_SourceCode,
  "Compliance Breach", "Missing compliance stamp for SOX Financial Regulations and
  Corporate IP Vault.")`. The write-discipline correctly fired **because the user
  explicitly asked to log**, targeted the highest-risk component, and grounded the
  finding in boundaries retrieved during the primary turn. This mutates the graph (adds
  one `Audit_Finding`), so the graph is no longer pristine after the run — re-seed to
  reset.

---

## Notes

**Leak-detection correctness (this iteration).** The fixed
`query_restricted_asset_leaks()` (`src/graph_tools.py`) now excludes the self-node
false positive and de-duplicates via canonical `c1.name < c2.name` ordering. Verified
directly: 4 distinct leaking assets / 6 paths, with `US_HQ_Mainframe_Vault`'s
dual-governance (Corporate_IP_Vault + SOX_Financial_Regs) no longer producing a
`Vault → Vault` phantom leak. The `src/graph_admin.py` security scans compute the same
distinct-asset set with the equivalent `c1 <> c2` guard.

**Provider switched to OpenAI for this run.** `LLM_PROVIDER=openai` → `gpt-4o-mini`.
The prior log ran on Google `gemini-3.5-flash`; both are supported via the `.env`
toggle in `src/llm.py`. This run recorded **zero** transient disconnects (the earlier
Gemini follow-up failures were upstream `Server disconnected` events, not code/data
defects).

**Harness cosmetic note.** `eval/run_testcases.py` prints a fixed
`"... (LIVE Gemini) ..."` banner regardless of the active provider; the actual model
this run was OpenAI `gpt-4o-mini` (confirmed via `src.llm.build_llm`). The banner
string is cosmetic and does not affect results — flagged for a future one-line fix.

**Reproduce:**
```
python seed_db.py                 # reset to pristine enriched seed
python eval/run_testcases.py      # writes eval/_results.json
```
Set `LLM_PROVIDER` in `.env` (`openai` or `google`) to pick the backend.
