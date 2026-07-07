# Cleanup Log — Lucid Lineage

**Date:** 2026-07-07

This log records housekeeping decisions from the repository-wide review. Per the
engagement rules, files that were *definitively* unused/redundant/deprecated would
be deleted; files that merely *appear* unused but are safer to keep are recorded
here with reasoning for human confirmation instead of being removed.

---

## Files reviewed and **DELETED** (maintainer-confirmed 2026-07-07)

### `query.py` (repository root) — DELETED
- **What it was:** A 5-line ad-hoc debug snippet that opened a raw Neo4j session and
  printed the outgoing relationships of `EU_Customer_PII_Master`.
- **Why removable:** Not imported by any module, not referenced in
  `README.md`/`ARCHITECTURE.md`, had no `if __name__ == "__main__"` guard, and
  duplicated functionality already provided by `check_asset_lineage` /
  `src.graph_tools.query_asset_lineage`.
- **Disposition:** Flagged for review, then **deleted after explicit maintainer confirmation**.

### `eval/run_benchmark.py` — DELETED
- **What it was:** An effectively empty file (no executable content).
- **Why removable:** Provided no functionality and was not imported anywhere.
- **Disposition:** Flagged as a possible Milestone B scaffold, then **deleted after
  explicit maintainer confirmation**. The `eval/` package now contains the functional
  test harness `run_testcases.py` added during this review.

---

## Dependency housekeeping (see `requirements.txt`)

The following were **removed** from `requirements.txt` because they are not directly
imported by the active code (this is dependency hygiene, not file deletion):

- `google-genai` — transitive dependency, pulled in automatically by `langchain-google-genai`.
- `langchain` (meta-package) — never imported; the code uses `langchain-classic`,
  `langchain-core`, and `langchain-google-genai`. `langchain-classic` does not require it.
- `pytest` — no test files in the repository import or use it. Re-add if/when a
  `pytest` suite is introduced.

`requests>=2.34.2` was **added** (directly imported by `check_models.py` but previously missing).

---

## Build artifacts (not tracked, left in place)

- `src/__pycache__/*.pyc` — Python bytecode caches. Already covered by `.gitignore`
  and regenerated automatically on import; not deleted (churn with no benefit).

---

**Summary:** Two files were deleted after maintainer confirmation
(`query.py`, `eval/run_benchmark.py`). No other files were removed.
