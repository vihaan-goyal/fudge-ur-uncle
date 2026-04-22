"""
Alert scoring formula.

    S = (T * V) * (alpha*D + beta*R + gamma*A) * (1 + delta*N)

Where:
    T = topic match (industry <-> vote category)     in [0, 1]
    V = vote proximity (exp decay on days until)     in [0, 1]
    D = donation magnitude (log-scaled)              in [0, 1]
    R = donation recency (exp decay on days since)   in [0, 1]
    A = anomaly factor (z-score vs baseline)         in [0, 1]
    N = news salience (article count, normalized)    in [0, 1]

Final score S lies in [0, 1.5] with default weights. Thresholds:
    S > 0.3 -> alert
    S > 0.6 -> urgent
"""

import math
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Optional

from .industry_map import topic_match


# ---------- Tunable constants ----------

ALPHA = 0.5        # weight on donation magnitude
BETA = 0.3         # weight on donation recency
GAMMA = 0.2        # weight on anomaly
DELTA = 0.5        # news boost coefficient (N doubles impact at most)

TAU_VOTE = 14.0    # days; vote proximity half-life ~ tau * ln(2) ~= 10 days
TAU_DONATION = 30.0  # days; donation recency half-life ~ 21 days

MAX_DONATION = 100_000.0  # amount that saturates D to 1.0
NEWS_SALIENCE_THRESHOLD = 25  # article count that saturates N to 1.0
ANOMALY_Z_CAP = 3.0  # clip z-scores at 3 sigma

ALERT_THRESHOLD = 0.3
URGENT_THRESHOLD = 0.6


# ---------- Input data shapes ----------

@dataclass
class Donation:
    amount: float
    donation_date: date
    industry: str
    pac_name: str


@dataclass
class ScheduledVote:
    bill_number: str
    title: str
    category: str
    scheduled_date: date


@dataclass
class Baseline:
    """Historical stats for (rep, industry). Used for anomaly detection."""
    mean_amount: float
    stddev_amount: float
    n_samples: int


@dataclass
class Signals:
    """All intermediate signal values. Stored on alert for explainability."""
    T: float
    V: float
    D: float
    R: float
    A: float
    N: float
    score: float
    urgent: bool


# ---------- Individual signal computations ----------

def compute_T(industry: str, category: str) -> float:
    """Topic match between donor industry and vote category."""
    return topic_match(industry, category)


def compute_V(vote_date: date, today: Optional[date] = None) -> float:
    """
    Vote proximity: exp(-days_until / TAU_VOTE).

    Returns 0 if the vote is in the past.
    """
    today = today or date.today()
    days_until = (vote_date - today).days
    if days_until < 0:
        return 0.0
    return math.exp(-days_until / TAU_VOTE)


def compute_D(amount: float) -> float:
    """Donation magnitude, log-scaled and normalized."""
    if amount <= 0:
        return 0.0
    numerator = math.log10(amount + 1)
    denominator = math.log10(MAX_DONATION + 1)
    return min(1.0, numerator / denominator)


def compute_R(donation_date: date, today: Optional[date] = None) -> float:
    """Donation recency: exp(-days_since / TAU_DONATION)."""
    today = today or date.today()
    days_since = max(0, (today - donation_date).days)
    return math.exp(-days_since / TAU_DONATION)


def compute_A(amount: float, baseline: Optional[Baseline]) -> float:
    """
    Anomaly factor: z-score vs. rep's historical donations from this industry.

    Returns 0.5 if no baseline (unknown, not flagged but not dismissed).
    Otherwise returns clip(z, 0, ANOMALY_Z_CAP) / ANOMALY_Z_CAP.
    """
    if baseline is None or baseline.n_samples < 3 or baseline.stddev_amount <= 0:
        return 0.5
    z = (amount - baseline.mean_amount) / baseline.stddev_amount
    z_clipped = max(0.0, min(ANOMALY_Z_CAP, z))
    return z_clipped / ANOMALY_Z_CAP


def compute_N(article_count: int) -> float:
    """News salience from count of articles mentioning the bill/topic."""
    if article_count <= 0:
        return 0.0
    return min(1.0, article_count / NEWS_SALIENCE_THRESHOLD)


# ---------- Main scoring function ----------

def score_alert(
    donation: Donation,
    vote: ScheduledVote,
    baseline: Optional[Baseline] = None,
    news_article_count: int = 0,
    today: Optional[date] = None,
) -> Signals:
    """
    Compute the full alert score for a (donation, vote) pair.

    Returns a Signals object with all intermediate values and the final score.
    """
    T = compute_T(donation.industry, vote.category)
    V = compute_V(vote.scheduled_date, today)

    # Gate: if no topic match or vote already past, short-circuit.
    if T == 0.0 or V == 0.0:
        return Signals(T=T, V=V, D=0, R=0, A=0, N=0, score=0.0, urgent=False)

    D = compute_D(donation.amount)
    R = compute_R(donation.donation_date, today)
    A = compute_A(donation.amount, baseline)
    N = compute_N(news_article_count)

    gate = T * V
    donation_signal = ALPHA * D + BETA * R + GAMMA * A
    news_boost = 1.0 + DELTA * N

    score = gate * donation_signal * news_boost

    return Signals(
        T=T, V=V, D=D, R=R, A=A, N=N,
        score=round(score, 4),
        urgent=score > URGENT_THRESHOLD,
    )


def should_alert(signals: Signals) -> bool:
    return signals.score > ALERT_THRESHOLD


def format_alert_text(
    donation: Donation, vote: ScheduledVote, signals: Signals
) -> tuple[str, str]:
    """Generate headline + body for an alert. Returns (headline, body)."""
    dollar = f"${donation.amount:,.0f}"
    industry_pretty = donation.industry.replace("_", " ").title()
    days_until = (vote.scheduled_date - (date.today())).days

    if signals.urgent:
        headline = (
            f"{dollar} from {industry_pretty} PACs — "
            f"{vote.category} vote in {days_until} days"
        )
    else:
        headline = (
            f"Recent {industry_pretty} donation ahead of {vote.category} vote"
        )

    body = (
        f"Your rep received {dollar} from {donation.pac_name} "
        f"({industry_pretty}) on {donation.donation_date.isoformat()}. "
        f"Bill {vote.bill_number} ({vote.title}) is scheduled for "
        f"{vote.scheduled_date.isoformat()}."
    )
    return headline, body


# ---------- Self-test ----------

if __name__ == "__main__":
    # Scenario: $75k from Exxon PAC 5 days ago, climate vote in 2 days, lots of news
    d = Donation(
        amount=75_000,
        donation_date=date.today() - timedelta(days=5),
        industry="oil_gas",
        pac_name="Exxon Mobil Corp PAC",
    )
    v = ScheduledVote(
        bill_number="S.1190",
        title="Clean Air Standards Modernization Act",
        category="environment",
        scheduled_date=date.today() + timedelta(days=2),
    )
    baseline = Baseline(mean_amount=10_000, stddev_amount=8_000, n_samples=12)

    sig = score_alert(d, v, baseline=baseline, news_article_count=30)
    print(f"Signals: {asdict(sig)}")
    print(f"Alert? {should_alert(sig)} (score={sig.score}, urgent={sig.urgent})")
    h, b = format_alert_text(d, v, sig)
    print(f"\nHeadline: {h}\nBody: {b}")