"""
Pipeline configuration.

All time windows and tunables for the alerts pipeline live here.
Defaults are sensible; override with env vars for cron / production use.
"""

import os


def _int_env(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        print(f"[config] Bad value for {name}={val!r}, using default {default}")
        return default


def _float_env(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        print(f"[config] Bad value for {name}={val!r}, using default {default}")
        return default


# How far back to consider donations when scoring.
# Default of 180 days is chosen because the FEC has a multi-week processing
# lag — by the time Q1 reports are public, the most recent donations are
# already 60-90 days old. 180 ensures we always have data to score.
# Donations older than this are skipped (their R signal would be ~0 anyway).
DONATION_LOOKBACK_DAYS = _int_env("ALERTS_DONATION_LOOKBACK_DAYS", 180)

# How far ahead to consider scheduled votes.
# Votes farther out than this are skipped (V signal would be near 0).
VOTE_LOOKAHEAD_DAYS = _int_env("ALERTS_VOTE_LOOKAHEAD_DAYS", 30)

# How far back to look for news mentions when computing the N signal.
NEWS_LOOKBACK_DAYS = _int_env("ALERTS_NEWS_LOOKBACK_DAYS", 7)

# Minimum number of historical donations from the same (rep, industry) needed
# before we trust the baseline. Below this, A signal falls back to 0.5.
BASELINE_MIN_SAMPLES = _int_env("ALERTS_BASELINE_MIN_SAMPLES", 3)

# State-side calibration. FTM aggregates are lifetime, stamped with today's
# date — so R would saturate to 1.0 for every state donation. Use a flat
# proxy value instead to reflect "donations from any point in the rep's
# career" rather than "donation arrived today." 0.4 sits between recent
# (~30 days, R~0.4) and stale (~90 days, R~0.05).
PROXY_DONATION_R = _float_env("ALERTS_PROXY_DONATION_R", 0.4)

# State actors rarely accumulate enough itemized donations to clear
# BASELINE_MIN_SAMPLES per industry, so their A signal almost always falls
# back to the default. The historical default of 0.5 ("unknown") inflates
# state scores; 0.0 ("we have no anomaly signal") is more honest.
NO_BASELINE_A_HONEST = _float_env("ALERTS_NO_BASELINE_A_HONEST", 0.0)


def print_config() -> None:
    print("[config] Pipeline windows:")
    print(f"  donation_lookback     = {DONATION_LOOKBACK_DAYS} days")
    print(f"  vote_lookahead        = {VOTE_LOOKAHEAD_DAYS} days")
    print(f"  news_lookback         = {NEWS_LOOKBACK_DAYS} days")
    print(f"  baseline_min_samples  = {BASELINE_MIN_SAMPLES}")
    print(f"  proxy_donation_r      = {PROXY_DONATION_R}  (state)")
    print(f"  no_baseline_a_honest  = {NO_BASELINE_A_HONEST}  (state)")