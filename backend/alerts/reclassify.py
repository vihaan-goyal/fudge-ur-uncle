"""
Re-run the classifier on every donation already in the DB.

When you update pac_classifier.py with new rules or known PACs, run this
to recompute the industry on existing rows. Saves having to re-ingest
from FEC (which takes minutes and uses API quota).

Usage:
    python -m backend.alerts.reclassify
    python -m backend.alerts.reclassify --only-unknown   # faster: only relabel current 'unknown' rows
"""

import argparse
from collections import Counter

try:
    from ..db import connect
except ImportError:
    from db import connect
from . import pac_classifier


def reclassify(only_unknown: bool = False) -> dict:
    where = "WHERE industry = 'unknown'" if only_unknown else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT id, pac_name, industry FROM donations {where}"
        ).fetchall()

        before = Counter(r["industry"] for r in rows)
        changes = {}
        for r in rows:
            new = pac_classifier.classify(r["pac_name"])
            if new != r["industry"]:
                changes[r["id"]] = new

        for rid, new_industry in changes.items():
            conn.execute(
                "UPDATE donations SET industry = ? WHERE id = ?",
                (new_industry, rid),
            )

        after = Counter()
        for r in rows:
            after[changes.get(r["id"], r["industry"])] += 1

    print(f"Scanned {len(rows)} donations ({'unknowns only' if only_unknown else 'all'})")
    print(f"Updated {len(changes)} rows")
    print("\nIndustry counts:")
    print(f"  {'INDUSTRY':<28} {'BEFORE':>7}  {'AFTER':>7}  CHANGE")
    print("  " + "-" * 60)
    all_keys = sorted(set(before) | set(after))
    for k in all_keys:
        b = before.get(k, 0)
        a = after.get(k, 0)
        delta = a - b
        sign = "+" if delta > 0 else ""
        print(f"  {k:<28} {b:>7}  {a:>7}  {sign}{delta}")

    # Top remaining unknowns
    if after.get("unknown", 0):
        print(f"\nTop 10 remaining unknown PACs by donation count:")
        with connect() as conn:
            for r in conn.execute(
                """SELECT pac_name, COUNT(*) AS n, SUM(amount) AS total
                   FROM donations WHERE industry = 'unknown'
                   GROUP BY pac_name ORDER BY total DESC LIMIT 10"""
            ):
                print(f"  ${r['total']:>10,.0f}  ({r['n']:>3}x)  {r['pac_name']}")

    return {"updated": len(changes), "before": dict(before), "after": dict(after)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only-unknown", action="store_true",
                   help="Only re-classify rows currently marked 'unknown' (faster)")
    args = p.parse_args()
    reclassify(only_unknown=args.only_unknown)