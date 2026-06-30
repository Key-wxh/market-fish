"""
Economic Alignment RL — Agent Bazaar 2026 principle.
市场信号驱动的 Agent 策略自适应

Key findings from Agent Bazaar (arXiv 2026):
- Economic alignment ≠ general capability. You don't need smarter agents —
  you need agents that respond correctly to market incentives.
- Simple RL on strategy dimensions outperforms complex prompt engineering.
- Market signals (adoption rate, churn, price trends) are the reward function.
- Personality persistence: RL adapts within bounds of agent type.

Strategy dimensions (5-axis):
1. price_sensitivity: how much price affects purchase (0=insensitive, 1=very sensitive)
2. early_adopter: tendency to buy new/unproven products (0=laggard, 1=innovator)
3. social_susceptibility: peer influence on decisions (0=independent, 1=follower)
4. loyalty: stick with purchased products (0=fickle, 1=loyal)
5. risk_tolerance: try risky products (0=conservative, 1=risk-seeking)

RL mechanism: Exponential Moving Average (EMA) on strategy values with
market-outcome rewards. Bounded by agent personality type.
"""

import random
from collections import defaultdict

# Learning rate for strategy adaptation
ALPHA = 0.08  # EMA weight for new observations

# Reward magnitudes
REWARD_SATISFIED_PURCHASE = 0.15       # Bought + happy → good decision
REWARD_RECOMMENDATION_MATCH = 0.12     # Recommended → peer also bought
PENALTY_CHURN = -0.20                  # Bought + churned → bad decision
PENALTY_MISSED_TREND = -0.08           # Didn't buy trending product peers bought
PENALTY_OVERPAID = -0.10               # Paid > market average → bad price sense

# Strategy bounds per agent type (personality persistence)
AGENT_TYPE_STRATEGY_BOUNDS = {
    "consumer": {
        "price_sensitivity": (0.3, 0.9),
        "early_adopter": (0.1, 0.8),
        "social_susceptibility": (0.2, 0.9),
        "loyalty": (0.1, 0.7),
        "risk_tolerance": (0.1, 0.7),
    },
    "smb": {
        "price_sensitivity": (0.5, 1.0),
        "early_adopter": (0.05, 0.4),
        "social_susceptibility": (0.1, 0.6),
        "loyalty": (0.3, 0.9),
        "risk_tolerance": (0.05, 0.4),
    },
    "enterprise": {
        "price_sensitivity": (0.4, 0.8),
        "early_adopter": (0.0, 0.2),
        "social_susceptibility": (0.0, 0.3),
        "loyalty": (0.5, 1.0),
        "risk_tolerance": (0.0, 0.2),
    },
    "competitor": {
        "price_sensitivity": (0.6, 1.0),
        "early_adopter": (0.3, 0.9),
        "social_susceptibility": (0.0, 0.3),
        "loyalty": (0.0, 0.3),
        "risk_tolerance": (0.5, 1.0),
    },
    "environment": {
        "price_sensitivity": (0.3, 0.7),
        "early_adopter": (0.2, 0.6),
        "social_susceptibility": (0.2, 0.6),
        "loyalty": (0.3, 0.7),
        "risk_tolerance": (0.2, 0.6),
    },
}

# Default bounds for unknown agent types
DEFAULT_BOUNDS = {
    "price_sensitivity": (0.2, 0.8),
    "early_adopter": (0.1, 0.7),
    "social_susceptibility": (0.1, 0.7),
    "loyalty": (0.1, 0.7),
    "risk_tolerance": (0.1, 0.7),
}


def init_strategy(agent_profile: dict) -> dict:
    """
    Initialize strategy vector for an agent based on their profile.
    Personality traits from agent profile map to initial strategy values.
    """
    agent_type = agent_profile.get("type", "consumer")
    tech = agent_profile.get("tech_savviness", 0.5)
    inf = agent_profile.get("influence_weight", 1.0)
    budget = agent_profile.get("budget_monthly_cny", 500)
    decision_speed = agent_profile.get("decision_speed", "days")
    bdi = agent_profile.get("bdi", {})

    bounds = AGENT_TYPE_STRATEGY_BOUNDS.get(agent_type, DEFAULT_BOUNDS)

    # Initialize from profile traits with some randomness
    def bounded_init(key: str, base: float) -> float:
        lo, hi = bounds[key]
        noise = random.uniform(-0.08, 0.08)
        return max(lo, min(hi, base + noise))

    # Derive initial values from agent profile
    # Higher tech_savviness → earlier adopter, higher risk tolerance
    # Higher influence_weight → lower social susceptibility (leaders, not followers)
    # Larger budget → less price sensitive
    # "impulse" decision speed → higher early adopter, lower loyalty
    # More desires in BDI → higher risk tolerance

    price_sens = bounded_init("price_sensitivity",
        1.0 - min(budget / 2000, 0.8))  # Higher budget → less sensitive
    early_adopt = bounded_init("early_adopter",
        tech * 0.6 + (0.3 if decision_speed == "impulse" else 0.0))
    social_susc = bounded_init("social_susceptibility",
        max(0.2, 1.0 - inf * 0.3))  # High influence → less susceptible
    loyalty = bounded_init("loyalty",
        0.3 + (0.2 if decision_speed in ("weeks", "months") else 0.0))
    risk_tol = bounded_init("risk_tolerance",
        tech * 0.5 + len(bdi.get("desires", [])) * 0.05)

    return {
        "price_sensitivity": round(price_sens, 3),
        "early_adopter": round(early_adopt, 3),
        "social_susceptibility": round(social_susc, 3),
        "loyalty": round(loyalty, 3),
        "risk_tolerance": round(risk_tol, 3),
    }


def update_strategy(agent_id: str, agent_states: dict, market_signals: dict,
                    product_directions: list) -> dict:
    """
    Update one agent's strategy based on round outcomes.

    Reward signals:
    - Last purchase still active (not churned) → reward loyalty + risk tolerance
    - Churned a product → penalize loyalty, adjust price sensitivity
    - Recommended and peer bought → reward social influence alignment
    - Missed trending product → penalize, increase early_adopter
    - Paid above market average → adjust price_sensitivity up

    Returns updated strategy dict.
    """
    state = agent_states.get(agent_id)
    if not state:
        return {}

    profile = state.get("profile", {})
    agent_type = profile.get("type", "consumer")
    bounds = AGENT_TYPE_STRATEGY_BOUNDS.get(agent_type, DEFAULT_BOUNDS)

    # Get or init strategy
    strategy = state.get("rl_strategy")
    if not strategy:
        strategy = init_strategy(profile)
        state["rl_strategy"] = strategy

    strategy = dict(strategy)  # Copy to mutate
    history = state.get("history", [])
    purchased = state.get("purchased_products", {})

    def clamp(key: str, val: float) -> float:
        lo, hi = bounds[key]
        return round(max(lo, min(hi, val)), 3)

    # ---- Reward signal 1: Purchase outcomes ----
    for pid, pinfo in purchased.items():
        if "churned_at" not in pinfo:
            # Active purchase → good decision
            strategy["loyalty"] = clamp("loyalty", strategy["loyalty"] + ALPHA * REWARD_SATISFIED_PURCHASE)
            strategy["risk_tolerance"] = clamp("risk_tolerance",
                strategy["risk_tolerance"] + ALPHA * REWARD_SATISFIED_PURCHASE * 0.5)
        else:
            # Churned → bad decision
            strategy["loyalty"] = clamp("loyalty", strategy["loyalty"] + ALPHA * PENALTY_CHURN)
            strategy["risk_tolerance"] = clamp("risk_tolerance",
                strategy["risk_tolerance"] + ALPHA * PENALTY_CHURN * 0.5)

    # ---- Reward signal 2: Price awareness ----
    if purchased and market_signals.get("adoption_rate", 0) > 0.1:
        # Check if agent overpaid relative to product's typical price
        for pid, pinfo in purchased.items():
            price_paid = pinfo.get("price_paid", 0)
            # Find product in directions
            for p in product_directions:
                if p.get("id") == pid:
                    est_price_str = p.get("estimated_pricing_cny", "0")
                    try:
                        est_price = float(est_price_str.replace("¥", "").split("-")[0].strip())
                        if est_price > 0 and price_paid > est_price * 1.5:
                            strategy["price_sensitivity"] = clamp("price_sensitivity",
                                strategy["price_sensitivity"] + ALPHA * 0.05)  # Become more price sensitive
                    except (ValueError, IndexError):
                        pass

    # ---- Reward signal 3: Social recommendation effectiveness ----
    my_recommendations = [h for h in history[-5:] if h.get("action") == "recommend"]
    if my_recommendations:
        # Check if any recommended peers later purchased
        rec_product = my_recommendations[-1].get("product_id")
        if rec_product:
            for conn_id in profile.get("social_network", {}).get("connections", []):
                if conn_id in agent_states:
                    conn_hist = agent_states[conn_id].get("history", [])
                    conn_bought = any(
                        h.get("action") == "purchase" and h.get("product_id") == rec_product
                        for h in conn_hist[-3:]
                    )
                    if conn_bought:
                        strategy["social_susceptibility"] = clamp("social_susceptibility",
                            strategy["social_susceptibility"] + ALPHA * REWARD_RECOMMENDATION_MATCH)

    # ---- Reward signal 4: Missed trends (FOMO learning) ----
    trending = market_signals.get("trending_products", [])
    if trending:
        my_purchases = set(purchased.keys())
        missed = set(trending) - my_purchases
        if missed:
            # Agent missed trending products → slightly increase early adopter tendency
            strategy["early_adopter"] = clamp("early_adopter",
                strategy["early_adopter"] + ALPHA * abs(PENALTY_MISSED_TREND) * 0.5)

    # ---- Reward signal 5: Market sentiment alignment ----
    sentiment = market_signals.get("avg_sentiment", 0)
    if sentiment > 0.3 and not purchased:
        # Market is optimistic but agent hasn't bought → increase risk tolerance slightly
        strategy["risk_tolerance"] = clamp("risk_tolerance",
            strategy["risk_tolerance"] + ALPHA * 0.03)
    elif sentiment < -0.3 and purchased:
        # Market is pessimistic but agent bought → decrease risk tolerance
        strategy["risk_tolerance"] = clamp("risk_tolerance",
            strategy["risk_tolerance"] + ALPHA * -0.03)

    state["rl_strategy"] = strategy
    return strategy


def update_all_strategies(agent_states: dict, market_signals: dict,
                          product_directions: list) -> dict:
    """
    Update RL strategies for all agents after a simulation round.
    Returns summary of strategy shifts.
    """
    shifts = defaultdict(list)

    for aid in agent_states:
        old_strategy = agent_states[aid].get("rl_strategy", {})
        new_strategy = update_strategy(aid, agent_states, market_signals, product_directions)

        if old_strategy and new_strategy:
            for key in new_strategy:
                delta = new_strategy[key] - old_strategy.get(key, new_strategy[key])
                if abs(delta) > 0.001:
                    shifts[key].append(delta)

    # Compute average shifts
    avg_shifts = {
        key: round(sum(vals) / len(vals), 4) if vals else 0.0
        for key, vals in shifts.items()
    }

    return {
        "agents_updated": len(agent_states),
        "avg_strategy_shifts": avg_shifts,
        "strategies_with_changes": sum(1 for v in shifts.values() if v),
    }


def get_strategy_context_for_decision(agent_id: str, agent_states: dict) -> str:
    """
    Generate a compact strategy context string to inject into the agent's decision prompt.
    This is how RL strategy affects LLM decisions — by providing behavioral guidance.
    """
    state = agent_states.get(agent_id)
    if not state:
        return ""

    strategy = state.get("rl_strategy")
    if not strategy:
        return ""

    lines = []
    ps = strategy["price_sensitivity"]
    if ps > 0.7:
        lines.append("You are price-sensitive. Prefer cheaper options.")
    elif ps < 0.3:
        lines.append("Price is not your main concern. Value quality over cost.")

    ea = strategy["early_adopter"]
    if ea > 0.6:
        lines.append("You are an early adopter. New products excite you.")
    elif ea < 0.2:
        lines.append("You prefer proven products. Avoid unvalidated new offerings.")

    ss = strategy["social_susceptibility"]
    if ss > 0.6:
        lines.append("Peer opinions strongly influence your decisions.")
    elif ss < 0.2:
        lines.append("You make independent decisions. Peer behavior doesn't sway you.")

    lo = strategy["loyalty"]
    if lo > 0.6:
        lines.append("Once you buy, you stick with it. Low churn risk.")
    elif lo < 0.2:
        lines.append("You churn easily if unsatisfied.")

    rt = strategy["risk_tolerance"]
    if rt > 0.6:
        lines.append("You take risks on unproven products.")
    elif rt < 0.2:
        lines.append("You are risk-averse. Only buy safe bets.")

    return " | ".join(lines) if lines else ""
