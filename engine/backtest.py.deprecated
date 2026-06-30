"""
[DEPRECATED] Backtest module — functionality merged into engine/calibrate.py.
Kept for reference. Use calibrate.py for pattern analysis and calibration.
"""

import json

# Known cases with verified outcomes
CASES = [
    {
        "name": "死了么 (Demumu)",
        "category": "consumer_app",
        "target": "consumer",
        "outcome": "success",
        "evidence": "4 days to #1 paid app, 60+ investors called. Built for $1500.",
        "key_factors": {
            "viral_name": True,
            "dead_simple_ux": True,
            "solves_real_fear": True,
            "social_sharing": True,
            "pricing": "¥1-8 one-time",
            "dev_cost": "$1500",
            "time_to_traction": "4 days",
        },
    },
    {
        "name": "小猫补光灯",
        "category": "consumer_app",
        "target": "consumer",
        "outcome": "success",
        "evidence": "1 hour build, hit #1 paid app on launch day.",
        "key_factors": {
            "viral_name": False,
            "dead_simple_ux": True,
            "solves_real_fear": False,
            "social_sharing": False,
            "pricing": "¥1 one-time",
            "dev_cost": "$0 (1 hour)",
            "time_to_traction": "1 day",
        },
    },
    {
        "name": "Pingo AI",
        "category": "consumer_app",
        "target": "consumer",
        "outcome": "success",
        "evidence": "$500K/month, 3M users, zero ads. All TikTok organic.",
        "key_factors": {
            "viral_name": False,
            "dead_simple_ux": True,
            "solves_real_fear": True,  # fear of speaking foreign language
            "social_sharing": True,   # roast mode went viral
            "pricing": "freemium → $9.99/mo",
            "dev_cost": "dorm room startup",
            "time_to_traction": "14 months",
        },
    },
    {
        "name": "GEO易",
        "category": "B2B_saas",
        "target": "smb",
        "outcome": "failure",
        "evidence": "223 detections, 0 paying users. B2B subscription with unclear ROI.",
        "key_factors": {
            "viral_name": False,
            "dead_simple_ux": False,  # needs explanation
            "solves_real_fear": False,  # brand visibility is abstract
            "social_sharing": False,
            "pricing": "¥99-1299/mo subscription",
            "dev_cost": "months of solo dev",
            "time_to_traction": "never",
        },
    },
    {
        "name": "卡路里拍照计算",
        "category": "consumer_app",
        "target": "consumer",
        "outcome": "success",
        "evidence": "Built by 17-year-old. $30M/year revenue.",
        "key_factors": {
            "viral_name": False,
            "dead_simple_ux": True,  # point camera at food
            "solves_real_fear": True,  # fear of getting fat
            "social_sharing": True,
            "pricing": "freemium",
            "dev_cost": "solo teen dev",
            "time_to_traction": "2 years",
        },
    },
]


def analyze_patterns() -> dict:
    """Extract success/failure patterns from known cases."""
    successes = [c for c in CASES if c["outcome"] == "success"]
    failures = [c for c in CASES if c["outcome"] == "failure"]

    # Factor analysis
    factors = ["dead_simple_ux", "solves_real_fear", "social_sharing", "viral_name"]
    success_rates = {}
    for f in factors:
        s_rate = sum(1 for c in successes if c["key_factors"].get(f)) / max(len(successes), 1)
        f_rate = sum(1 for c in failures if c["key_factors"].get(f)) / max(len(failures), 1)
        success_rates[f] = {"success_rate": round(s_rate, 2), "failure_rate": round(f_rate, 2)}

    # Category analysis
    categories = {}
    for c in CASES:
        cat = c["category"]
        if cat not in categories:
            categories[cat] = {"success": 0, "failure": 0}
        categories[cat][c["outcome"]] += 1

    # Pricing analysis
    pricing = {}
    for c in CASES:
        price = c["key_factors"]["pricing"]
        pricing[c["name"]] = {"price": price, "outcome": c["outcome"]}

    return {
        "cases_analyzed": len(CASES),
        "success_count": len(successes),
        "failure_count": len(failures),
        "factor_analysis": success_rates,
        "category_analysis": categories,
        "pricing_analysis": pricing,
        "key_finding": _derive_findings(successes, failures),
    }


def _derive_findings(successes: list, failures: list) -> str:
    """Derive success/failure rules from the data."""
    findings = []

    # Dead simple UX
    s_ux = sum(1 for c in successes if c["key_factors"]["dead_simple_ux"]) / len(successes)
    f_ux = sum(1 for c in failures if c["key_factors"]["dead_simple_ux"]) / len(failures)
    if s_ux > f_ux:
        findings.append(f"dead_simple_ux: {s_ux:.0%} of successes vs {f_ux:.0%} of failures")

    # Solves real fear
    s_fear = sum(1 for c in successes if c["key_factors"]["solves_real_fear"]) / len(successes)
    f_fear = sum(1 for c in failures if c["key_factors"]["solves_real_fear"]) / len(failures)
    if s_fear > f_fear:
        findings.append(f"solves_real_fear: {s_fear:.0%} vs {f_fear:.0%}")

    # Social sharing
    s_share = sum(1 for c in successes if c["key_factors"]["social_sharing"]) / len(successes)
    f_share = sum(1 for c in failures if c["key_factors"]["social_sharing"]) / len(failures)
    if s_share > f_share:
        findings.append(f"social_sharing: {s_share:.0%} vs {f_share:.0%}")

    # Consumer vs B2B
    s_consumer = sum(1 for c in successes if c["target"] == "consumer") / len(successes)
    findings.append(f"consumer_target: {s_consumer:.0%} of successes are B2C")

    return "; ".join(findings)


if __name__ == "__main__":
    result = analyze_patterns()
    print(json.dumps(result, indent=2, ensure_ascii=False))
