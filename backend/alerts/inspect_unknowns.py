"""
Show top unclassified PACs in the donations table.

Useful for finding gaps in pac_classifier.py: the highest-volume unknowns
are the ones worth adding to KNOWN_PACS or KEYWORD_RULES.

Usage:
    python -m backend.alerts.inspect_unknowns
    python -m backend.alerts.inspect_unknowns --limit 50
"""

import argparse

from ..db import connect


def inspect(limit: int = 30) -> None:
    with connect() as conn:
        rows = conn.execute(
            """SELECT pac_name,
                      COUNT(*) AS n_donations,
                      SUM(amount) AS total_dollars,
                      MAX(donation_date) AS most_recent
               FROM donations
               WHERE industry = 'unknown'
               GROUP BY pac_name
               ORDER BY total_dollars DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        if not rows:
            print("No unknown-industry donations in the database.")
            return

        print(f"\nTop {len(rows)} unclassified PACs by total dollars:\n")
        print(f"{'$ TOTAL':>12} {'#':>5}  {'LAST SEEN':>10}  PAC NAME")
        print("-" * 100)
        for r in rows:
            total = r["total_dollars"] or 0
            n = r["n_donations"]
            last = str(r["most_recent"])[:10]
            name = r["pac_name"][:65]
            print(f"${total:>11,.0f} {n:>5}  {last:>10}  {name}")

        # Summary stats (must stay inside the `with` block so conn is open)
        summary = conn.execute(
            """SELECT
                 SUM(CASE WHEN industry = 'unknown' THEN 1 ELSE 0 END) AS unk_n,
                 COUNT(*) AS total_n,
                 SUM(CASE WHEN industry = 'unknown' THEN amount ELSE 0 END) AS unk_d,
                 SUM(amount) AS total_d
               FROM donations"""
        ).fetchone()
        if summary["total_n"]:
            pct_n = 100 * summary["unk_n"] / summary["total_n"]
            pct_d = 100 * (summary["unk_d"] or 0) / (summary["total_d"] or 1)
            print(f"\nUnknown share: {pct_n:.1f}% of records, {pct_d:.1f}% of dollars")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=30)
    args = p.parse_args()
    inspect(args.limit)