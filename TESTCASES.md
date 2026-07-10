# Lucid Lineage Automated Test Cases

## Test Case 1: Asset Lineage & Location Co-Location
* **Primary Question:** "Trace the data lineage for the Supply_Chain_Manifest asset. Are there any active sovereign boundary breaches?"
* **Follow-up Question:** "Are there any other assets currently sitting in that exact same destination location?"

## Test Case 2: Macro Leak Auditing & Policy Mapping
* **Primary Question:** "Run a full compliance audit across the network. Are any assets classified as 'Highly_Restricted' leaking across geographical boundaries?"
* **Follow-up Question:** "What specific data security policy governs the gateway node where that leak was detected?"

## Test Case 3: Upstream Dependency & Mutation Verification
* **Primary Question:** "Identify all upstream dependencies feeding directly into the APAC gateway location. Which source components are responsible for that pipeline?"
* **Follow-up Question:** "Log an official audit finding for the highest-risk upstream component indicating a missing compliance stamp."

## Test Case 4: Context-Drift Node Resolution (single session)

> **Must run all three turns in the SAME session.** This scenario specifically
> reproduces the cross-turn context drift that a fresh-session-per-scenario harness
> cannot catch: after two turns anchored on a *different* APAC node, an ambiguous
> "APAC gateway" reference in a follow-up must still resolve to `APAC_Edge_Gateway`,
> not to the node the earlier turns were about.

* **Primary Question:** "Trace the lineage of Cardholder_Transaction_Vault and flag any cross-boundary leaks."
* **Follow-up 1:** "What compliance policy governs that analytics node it replicates to?"  *(steers context toward `APAC_Singapore_Analytics` / `APAC_Data_Sovereignty`)*
* **Follow-up 2 (the trap):** "Identify all upstream dependencies feeding directly into the APAC gateway location. Which source components are responsible for that pipeline?"  *(verbatim the original failing question — a one-to-one regression test)*
  * **Expected:** resolves "APAC gateway" to **`APAC_Edge_Gateway`** (NOT `APAC_Singapore_Analytics`), lists the `REPLICATED_TO` feeders `Global_Supply_Telemetry` and `APAC_Regional_Sales`, **and** traces them back to the responsible source components **`US_HQ_Mainframe_Vault`** (via Global_Supply_Telemetry) and **`APAC_Tokyo_Cloud_01`** (via APAC_Regional_Sales).