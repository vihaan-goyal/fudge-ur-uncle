"""Interactive helper to expand backend/data/ftm_eids.csv.

For each Legiscan-roster legislator that isn't already in the CSV, this
script opens a Google search for the FTM entity page in your browser,
then prompts you to paste the eid (or hit Enter to skip).

Usage (from project root):
    py scripts/find_ftm_eids.py CT House
    py scripts/find_ftm_eids.py NJ Senate

What you do per rep:
    1. Browser opens a Google search ranked to FTM entity-detail pages.
    2. Click the link whose title matches "<LASTNAME>, <FIRSTNAME>".
    3. The URL contains `eid=NNNNNNNN` — copy just the number.
    4. Paste at the prompt and press Enter. Or press Enter alone to skip.
    5. Type 'q' + Enter to quit (progress is saved continuously).

The CSV is appended in place; existing rows are never modified.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
import urllib.parse
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "backend" / "data" / "whoboughtmyrep.sqlite"
CSV_PATH = ROOT / "backend" / "data" / "ftm_eids.csv"


def chamber_norm(c: str) -> str:
    cl = c.strip().lower()
    if cl in ("rep", "representative", "house", "assemblyman", "assemblywoman", "assembly"):
        return "House"
    if cl in ("sen", "senator", "senate"):
        return "Senate"
    return c.strip()


def load_existing() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Return (full-name set, surname set) for dedup, both keyed by state."""
    full: set[tuple[str, str]] = set()
    surname: set[tuple[str, str]] = set()
    with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            st = row["state"].upper()
            nm = row["name"].lower().strip()
            full.add((st, nm))
            surname.add((st, nm.split()[-1]))
    return full, surname


def list_gaps(state: str, chamber: str) -> list[tuple[str, str, str, str]]:
    """Return [(state, chamber, name, district), ...] not already in the CSV."""
    full, surname = load_existing()
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT cache_key, value_json FROM ai_cache WHERE cache_key LIKE 'legiscan:people:%'"
    ).fetchall()
    out: list[tuple[str, str, str, str]] = []
    for key, value_json in rows:
        st = key.split(":")[-1].upper()
        if st != state.upper():
            continue
        people = json.loads(value_json)
        if not isinstance(people, list):
            continue
        for p in people:
            if not isinstance(p, dict):
                continue
            ch = chamber_norm(p.get("role") or p.get("chamber") or "")
            if ch != chamber:
                continue
            name = (p.get("name") or "").strip()
            if not name:
                continue
            last = name.lower().split()[-1]
            if (st, name.lower()) in full or (st, last) in surname:
                continue
            district = p.get("district") or ""
            out.append((st, ch, name, district))
    return out


def google_url(name: str) -> str:
    """Build a `site:followthemoney.org "LASTNAME, FIRSTNAME"` search URL."""
    parts = name.strip().split()
    if len(parts) < 2:
        # Fallback: search the whole name
        q = f'site:followthemoney.org "{name}"'
    else:
        last = parts[-1].upper()
        first = parts[0].upper()
        q = f'site:followthemoney.org "{last}, {first}"'
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)


def append_row(state: str, chamber: str, name: str, eid: str) -> None:
    with CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        # csv.writer normalizes quoting/escaping if names ever contain commas.
        csv.writer(f).writerow([state, chamber, name, eid])


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: py scripts/find_ftm_eids.py <STATE> <CHAMBER>")
        print("example: py scripts/find_ftm_eids.py CT House")
        return 1
    state = sys.argv[1].upper()
    chamber = sys.argv[2]
    if chamber not in ("House", "Senate"):
        print("chamber must be 'House' or 'Senate'")
        return 1

    gaps = list_gaps(state, chamber)
    if not gaps:
        print(f"No gaps for {state} {chamber} — directory is full.")
        return 0

    print(f"{len(gaps)} gap reps for {state} {chamber}.")
    print("Per rep: browser opens a Google search. Click the matching FTM link,")
    print("copy the eid (the number after `eid=` in the URL), paste below.")
    print("Enter alone = skip. 'q' = quit.\n")

    added = 0
    skipped = 0
    for i, (st, ch, name, district) in enumerate(gaps, 1):
        url = google_url(name)
        label = f"[{i}/{len(gaps)}] {name}"
        if district:
            label += f"  ({district})"
        print(label)
        webbrowser.open(url)
        try:
            ans = input("  eid> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\naborted.")
            break
        if ans.lower() == "q":
            print("quit.")
            break
        if not ans:
            skipped += 1
            continue
        if not ans.isdigit():
            print(f"  not a number, skipping: {ans!r}")
            skipped += 1
            continue
        append_row(st, ch, name, ans)
        added += 1
        print(f"  + appended {name} -> {ans}")

    print(f"\nDone. Added {added}, skipped {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
