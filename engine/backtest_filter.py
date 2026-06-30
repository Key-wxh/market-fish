"""
Backtest Filter — applies known success/failure factors from 5-case validation.
Factors with 100% success rate (dead_simple_ux, consumer_b2c) are hard filters.
Factors with 75% success rate (solves_real_fear, social_sharing) are soft signals.
"""

import json
from engine.config import backtest_cfg as _cfg

# Hard filters — 100% success vs 0% failure in backtest
HARD_PASS = [
    "dead_simple_ux",    # One action, no learning curve
    "consumer_b2c",      # Consumer market (not B2B)
]

# Soft signals — 75%+ correlation with success
SOFT_SIGNAL = [
    "solves_real_fear",   # Solves an emotional/safety fear
    "social_sharing",     # Built-in sharing mechanic
]

# Kill signals — 100% failure rate in backtest
HARD_FAIL = [
    "b2b_subscription",   # B2B SaaS subscription model
    "high_price_monthly",  # > ¥100/month
    "requires_onboarding", # Needs explanation or training
]


def score_direction(direction: dict) -> dict:
    """
    Score a product direction against backtest-validated success factors.
    Returns the direction with added backtest_score and flags.
    """
    name = direction.get("name", "")
    category = direction.get("category", "")
    target = direction.get("target_market", "")
    pricing = direction.get("estimated_pricing_cny", "")
    desc = json.dumps(direction, ensure_ascii=False).lower()

    score = 0
    flags = []

    # Hard passes
    # 1. Dead simple UX?
    ux_signals = ["one-click", "single action", "auto", "instant", "no login", "no signup",
                  "one tap", "voice", "photo", "screenshot", "scan"]
    if any(s in desc for s in ux_signals) or category in ("consumer_app", "mini_program", "browser_extension"):
        score += _cfg()["hard_pass_simple_ux"]
        flags.append("simple_ux")
    else:
        flags.append("complex_ux")

    # 2. Consumer B2C?
    if target == "consumer":
        score += _cfg()["hard_pass_simple_ux"]
        flags.append("consumer_target")
    elif target == "smb" and "one-time" in pricing.lower():
        score += 10  # Partial — SMB with one-time pricing is better than subscription
        flags.append("smb_onetime")

    # Soft signals
    # 3. Solves real fear?
    fear_signals = ["fear", "anxiety", "lonely", "die", "death", "safety", "security",
                    "embarrass", "shame", "lose", "lost", "forget", "miss", "scared",
                    "emotional", "feel", "stress", "pressure", "anxious"]
    if any(s in desc for s in fear_signals):
        score += 15
        flags.append("solves_fear")

    # 4. Social sharing?
    share_signals = ["share", "viral", "social", "friend", "wechat moment", "朋友圈",
                     "recommend", "invite", "challenge", "leaderboard", "group"]
    if any(s in desc for s in share_signals):
        score += 15
        flags.append("social_sharing")

    # Kill signals
    kill_flags = []
    if target == "smb" and ("/month" in pricing or "subscription" in desc):
        kill_flags.append("b2b_subscription")
        score -= 40
    if "¥" in pricing:
        try:
            price_str = pricing.replace("¥", "").replace(",", "").split("-")[0].strip()
            price = int(price_str)
            if price > 100 and "month" in pricing.lower():
                kill_flags.append("high_price_monthly")
                score -= 20
        except (ValueError, IndexError):
            pass

    return {
        **direction,
        "backtest_score": max(0, score),
        "backtest_flags": flags,
        "backtest_kill_flags": kill_flags,
        "backtest_verdict": "promising" if score >= 50 and not kill_flags else
                           "risky" if score >= 30 else "likely_fail",
    }


def filter_and_rank(directions: list) -> list:
    """Score all directions and rank by backtest alignment."""
    scored = [score_direction(d) for d in directions]
    # Sort: highest score first, kill-flagged last
    scored.sort(key=lambda d: (len(d.get("backtest_kill_flags", [])), -d["backtest_score"]))
    return scored
