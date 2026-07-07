"""
Lucid Lineage — One-shot database seeder (CLI).

Wipes and re-seeds the Neo4j graph from `data/init_graph.cypher` and captures a
drift-detection baseline. Delegates to `src.graph_admin.reset_graph` so the CLI,
the Streamlit "Reset Graph" button, and the app all share identical logic.

    python seed_db.py
"""

import sys

from src.graph_admin import reset_graph

# Windows consoles default to cp1252 and cannot encode the ✅/⚠️ status glyphs.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run_seed():
    summary = reset_graph()
    print(f"Database seeded: {summary['statements_executed']} statement(s) executed.")
    if summary["errors"]:
        print(f"⚠️  {len(summary['errors'])} statement error(s):")
        for e in summary["errors"]:
            print(f"   - {e}")
    else:
        print(f"✅ No errors. Baseline fingerprint captured ({summary['baseline']}…).")


if __name__ == "__main__":
    run_seed()
