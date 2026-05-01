"""
Seed sample data into the SQLite DB.

Run once after init_db() so the first pipeline run produces visible alerts.
Idempotent: skips rows that already exist (donations are deduped by
fec_filing_id, votes by bill_number, news by url).
"""

from datetime import date, datetime, timedelta

from ..db import connect


def _seed_donations(conn) -> int:
    """Sample PAC donations across a few legislators and industries."""
    today = date.today()
    rows = [
        # Sen. Murphy (CT) - small oil donation 5 days ago, urgent for climate vote
        ("M001169", "Exxon Mobil Corp PAC", "oil_gas", 75_000.0,
         today - timedelta(days=5), "FEC-2026-0001"),
        # Murphy historical baseline data (smaller amounts)
        ("M001169", "Chevron PAC", "oil_gas", 8_000.0,
         today - timedelta(days=200), "FEC-2025-0099"),
        ("M001169", "Marathon PAC", "oil_gas", 12_000.0,
         today - timedelta(days=300), "FEC-2025-0050"),
        ("M001169", "BP PAC", "oil_gas", 9_500.0,
         today - timedelta(days=400), "FEC-2025-0010"),

        # Sen. Blumenthal (CT) - pharma donation, drug pricing vote upcoming
        ("B001277", "Pfizer PAC", "pharmaceuticals", 50_000.0,
         today - timedelta(days=10), "FEC-2026-0002"),

        # Rep. Himes (CT) - bank donation, far from any vote
        ("H001047", "JPMorgan Chase PAC", "commercial_banks", 25_000.0,
         today - timedelta(days=20), "FEC-2026-0003"),

        # Sen. Blunt (MO) - defense donation 2 days ago, defense vote tomorrow
        ("B000575", "Lockheed Martin PAC", "defense_aerospace", 100_000.0,
         today - timedelta(days=2), "FEC-2026-0004"),
    ]

    inserted = 0
    for row in rows:
        try:
            conn.execute(
                """INSERT INTO donations
                   (actor_id, pac_name, industry, amount, donation_date, fec_filing_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
            inserted += 1
        except Exception:
            pass  # already exists
    return inserted


def _seed_votes(conn) -> int:
    """Sample upcoming scheduled votes."""
    today = date.today()
    rows = [
        ("S.1190", "Clean Air Standards Modernization Act", "environment",
         today + timedelta(days=2), "senate"),
        ("S.872", "Prescription Drug Pricing Reform Act", "healthcare",
         today + timedelta(days=7), "senate"),
        ("S.441", "Social Security Stabilization Act", "economy",
         today + timedelta(days=21), "senate"),
        ("H.R.1500", "Defense Authorization Supplemental", "defense",
         today + timedelta(days=1), "house"),
        ("S.2200", "Infrastructure Reauthorization", "infrastructure",
         today + timedelta(days=45), "senate"),  # outside lookahead window
    ]

    inserted = 0
    for row in rows:
        try:
            conn.execute(
                """INSERT INTO scheduled_votes
                   (bill_number, title, category, scheduled_date, chamber)
                   VALUES (?, ?, ?, ?, ?)""",
                row,
            )
            inserted += 1
        except Exception:
            pass
    return inserted


def _seed_news(conn) -> int:
    """Sample news mentions for the N (news salience) signal."""
    now = datetime.now()
    rows = [
        # Climate bill - heavy coverage (drives N -> 1.0)
        ("S.1190", "environment", "NYT",
         "https://example.com/nyt/clean-air-1", "Clean Air vote nears",
         now - timedelta(days=1)),
        ("S.1190", "environment", "Reuters",
         "https://example.com/reuters/clean-air", "Senate to vote on emissions",
         now - timedelta(days=2)),
        ("S.1190", "environment", "WaPo",
         "https://example.com/wapo/clean-air", "Battle lines drawn on Clean Air",
         now - timedelta(days=2)),
    ]
    # Bulk up climate coverage so N saturates
    for i in range(30):
        rows.append((
            "S.1190", "environment", f"src{i}",
            f"https://example.com/source{i}/climate",
            f"Coverage of climate vote #{i}",
            now - timedelta(days=(i % 7)),
        ))

    # Lighter coverage on the drug pricing bill
    rows.extend([
        ("S.872", "healthcare", "Politico",
         "https://example.com/politico/drug-prices", "Drug pricing fight",
         now - timedelta(days=3)),
        ("S.872", "healthcare", "STAT",
         "https://example.com/stat/pricing", "Pharma lobbies hard",
         now - timedelta(days=2)),
    ])

    inserted = 0
    for row in rows:
        try:
            conn.execute(
                """INSERT INTO news_mentions
                   (bill_number, topic, source, url, headline, published_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
            inserted += 1
        except Exception:
            pass
    return inserted


def seed_all() -> None:
    with connect() as conn:
        d = _seed_donations(conn)
        v = _seed_votes(conn)
        n = _seed_news(conn)
    print(f"[seed] Inserted {d} donations, {v} votes, {n} news mentions")


if __name__ == "__main__":
    seed_all()