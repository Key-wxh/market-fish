"""
BDI v2 Cognitive Architecture — v6 Step 6.

TwinMarket (NeurIPS 2025, arxiv 2502.01506): 6-step daily loop replacing
the simple one-shot decision prompt.

Steps: Belief → Desire → Intention → Action → Response → Update

Behavioral biases:
  - Overconfidence: agents overestimate positive outcomes by ~15%
  - Loss aversion: losses feel ~2x worse than gains
  - Herding: agents follow peer majority when uncertain
"""
import random
from engine.config import get_config


def bdi_decision_context(agent_profile: dict, state: dict, round_num: int,
                         products: list, market_sentiment: float = 0) -> str:
    """Generate the 6-step BDI context for an agent's decision prompt.

    Returns a string to inject into the LLM decision prompt.
    """
    cfg = get_config().get("bdi_v2", {})
    if not cfg.get("enabled", False):
        return ""

    bdi = agent_profile.get("bdi", {})
    beliefs = bdi.get("beliefs", ["Quality matters more than price"])
    desires = bdi.get("desires", ["Find the best product for my needs"])
    intentions = state.get("active_intentions", ["Evaluate available products"])
    biases = _get_active_biases(agent_profile, cfg)

    lines = [
        "\n=== BDI COGNITIVE MODEL (6-step loop) ===",
        "",
        "Step 1 — BELIEFS (what you think is true):",
    ]
    for b in beliefs[:3]:
        lines.append(f"  * {b}")

    lines.append("\nStep 2 — DESIRES (what you want):")
    for d in desires[:3]:
        lines.append(f"  * {d}")

    lines.append("\nStep 3 — INTENTIONS (what you plan to do):")
    for i in (intentions or ["Evaluate products"])[:3]:
        lines.append(f"  * {i}")

    lines.extend([
        "\nStep 4 — ACTION: Make ONE decision now based on your beliefs, desires, and intentions.",
        "\nStep 5 — RESPONSE: After acting, observe the outcome.",
        "\nStep 6 — UPDATE: Adjust beliefs/desires/intentions based on results.",
        "",
        "=== BEHAVIORAL BIASES (affect your judgment) ===",
    ])
    for bias_name, bias_desc in biases:
        lines.append(f"  * {bias_name}: {bias_desc}")

    lines.append(f"\nMarket sentiment: {'bullish' if market_sentiment > 0.2 else 'bearish' if market_sentiment < -0.2 else 'neutral'}")

    return "\n".join(lines)


def _get_active_biases(profile: dict, cfg: dict) -> list[tuple[str, str]]:
    """Determine which biases are active for this agent based on profile and config."""
    biases = []
    # Overconfidence: higher tech_savviness → more overconfident
    tech = float(profile.get("tech_savviness", 0.5))
    if cfg.get("overconfidence_enabled", True) and tech > 0.4:
        level = "strong" if tech > 0.7 else "moderate"
        biases.append(("Overconfidence", f"{level} — you tend to overestimate your judgment"))

    # Loss aversion: innate bias, ~2x
    if cfg.get("loss_aversion_enabled", True):
        income = float(profile.get("budget_monthly_cny", 500))
        if income < 600:
            strength = "high — losing money hurts significantly"
        elif income < 2000:
            strength = "moderate — you dislike losses more than you enjoy gains"
        else:
            strength = "mild — you can tolerate some losses"
        biases.append(("Loss Aversion", strength))

    # Herding: higher social_susceptibility in RL → more herding
    if cfg.get("herding_enabled", True):
        inf = float(profile.get("influence_weight", 1.0))
        if inf > 1.5:
            biases.append(("Herding", "strong — peer behavior strongly influences you"))
        elif inf > 0.8:
            biases.append(("Herding", "moderate — you notice what others do"))

    return biases


def update_bdi_intentions(agent_id: str, state: dict, decision: dict, round_num: int):
    """Update agent's active intentions based on the decision outcome (Step 6: Update).

    Called after each round's decision is processed.
    """
    cfg = get_config().get("bdi_v2", {})
    if not cfg.get("enabled", False):
        return

    action = decision.get("action", "")
    max_intentions = cfg.get("max_concurrent_intentions", 3)
    persistence = cfg.get("intention_persistence_rounds", 5)

    intentions = state.get("active_intentions", [])
    if not isinstance(intentions, list):
        intentions = []

    # Remove stale intentions
    intentions = [i for i in intentions if not isinstance(i, str) or
                  not i.startswith("_done_")]

    # Add new intention based on action
    product = decision.get("product_id", "")
    if action == "purchase":
        intentions.append(f"Evaluate satisfaction with {product}")
    elif action == "discover":
        intentions.append(f"Compare {product} with alternatives")
    elif action == "churn":
        intentions.append(f"Find replacement for {product}")
        intentions.append("_done_churned")  # Mark old intention as resolved

    # Trim to max concurrent
    intentions = [i for i in intentions if not i.startswith("_done_")]
    intentions = intentions[-max_intentions:]

    # Add persistence tag
    intentions = [f"{i} (persists {persistence} rounds)" if not i.endswith(")") else i
                  for i in intentions]

    state["active_intentions"] = intentions
