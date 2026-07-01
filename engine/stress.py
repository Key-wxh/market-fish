"""
Cross-Domain Stress Model — v6 Step 7 (part 1).

EconSimulacra (2026, arxiv 2606.26883): Shared stress states across agents.
Financial pressure, social comparison, information overload, and emotional
contagion combine to produce a per-agent stress level that modulates WTP.

Stress → WTP mapping:
  low stress: +10% WTP (calm, confident spending)
  moderate: -10% WTP (cautious)
  high: -30% WTP (freeze spending)
  extreme: -60% WTP (crisis mode)
"""
from engine.config import get_config


def compute_stress(agent_state: dict, market_context: dict) -> float:
    """Compute stress level (0-1) for one agent.

    Factors:
      - Financial pressure: how much of budget is spent
      - Social comparison: peers doing better/worse
      - Information overload: too many products discovered
      - Emotional contagion: negative market sentiment
    """
    cfg = get_config().get("stress", {})
    if not cfg.get("enabled", False):
        return 0.0

    weights = cfg.get("model", {})
    profile = agent_state.get("profile", {})

    # Financial pressure
    budget = float(profile.get("budget_monthly_cny", 500))
    spent = float(agent_state.get("total_spent", 0))
    financial = min(1.0, spent / max(budget, 1)) if budget > 0 else 0
    financial *= weights.get("financial_pressure_weight", 0.4)

    # Social comparison
    coupling = agent_state.get("coupling_context", {})
    peer_sentiment = coupling.get("peer_sentiment", 0)
    social = max(0, -peer_sentiment) * 0.5  # Negative peer sentiment = stress
    social *= weights.get("social_comparison_weight", 0.3)

    # Information overload
    discovered = len(agent_state.get("discovered_products", set()))
    overload = min(1.0, discovered / 10) * 0.5
    overload *= weights.get("information_overload_weight", 0.2)

    # Emotional contagion from market
    market_sentiment = coupling.get("market_sentiment", 0)
    contagion = max(0, -market_sentiment)
    contagion *= weights.get("emotional_contagion_weight", 0.1)

    return round(min(1.0, financial + social + overload + contagion), 2)


def stress_to_wtp_multiplier(stress_level: float) -> float:
    """Convert stress level to willingness-to-pay multiplier."""
    cfg = get_config().get("stress", {}).get("stress_to_wtp_map", {})
    if stress_level <= 0.2:
        return cfg.get("low", 1.10)
    elif stress_level <= 0.5:
        return cfg.get("moderate", 0.90)
    elif stress_level <= 0.8:
        return cfg.get("high", 0.70)
    else:
        return cfg.get("extreme", 0.40)


def apply_stress(agent_states: dict, market_context: dict) -> dict:
    """Apply stress computation to all agents. Returns {agent_id: stress_level}."""
    cfg = get_config().get("stress", {})
    if not cfg.get("enabled", False):
        return {}

    stress_levels = {}
    for aid, state in agent_states.items():
        sl = compute_stress(state, market_context)
        state["stress_level"] = sl
        stress_levels[aid] = sl
    return stress_levels
