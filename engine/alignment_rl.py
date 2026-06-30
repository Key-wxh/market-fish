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
from engine.config import rl_cfg as _cfg


def init_strategy(agent_profile: dict) -> dict:
    """
    Initialize strategy vector for an agent based on their profile.
    Personality traits from agent profile map to initial strategy values.
    """
    agent_type = agent_profile.get("type", "consumer")
    tech = float(agent_profile.get("tech_savviness", 0.5))
    inf = float(agent_profile.get("influence_weight", 1.0))
    budget = float(agent_profile.get("budget_monthly_cny", 500))
    decision_speed = str(agent_profile.get("decision_speed", "days"))
    bdi = agent_profile.get("bdi", {})

    bounds = _cfg()["agent_type_bounds"].get(agent_type, _cfg()["agent_type_bounds"]["default"])

    # Initialize from profile traits with some randomness
    def bounded_init(key: str, base: float) -> float:
        lo, hi = bounds[key]
        noise = random.uniform(-_cfg()["init_noise_range"], _cfg()["init_noise_range"])
        return max(lo, min(hi, base + noise))

    # Derive initial values from agent profile
    # Higher tech_savviness → earlier adopter, higher risk tolerance
    # Higher influence_weight → lower social susceptibility (leaders, not followers)
    # Larger budget → less price sensitive
    # "impulse" decision speed → higher early adopter, lower loyalty
    # More desires in BDI → higher risk tolerance

    price_sens = bounded_init("price_sensitivity",
        1.0 - min(budget / _cfg()["budget_price_sens_divisor"], _cfg()["budget_price_sens_cap"]))  # Higher budget → less sensitive
    early_adopt = bounded_init("early_adopter",
        tech * _cfg()["tech_early_adopter_factor"] + (_cfg()["impulse_early_adopter_bonus"] if decision_speed == "impulse" else 0.0))
    social_susc = bounded_init("social_susceptibility",
        max(_cfg()["high_influence_susceptibility_min"], 1.0 - inf * _cfg()["influence_susceptibility_factor"]))  # High influence → less susceptible
    loyalty = bounded_init("loyalty",
        _cfg()["base_loyalty"] + (_cfg()["slow_decision_loyalty_bonus"] if decision_speed in ("weeks", "months") else 0.0))
    risk_tol = bounded_init("risk_tolerance",
        tech * _cfg()["tech_risk_tolerance_factor"] + len(bdi.get("desires", [])) * _cfg()["desires_risk_tolerance_factor"])

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
    bounds = _cfg()["agent_type_bounds"].get(agent_type, _cfg()["agent_type_bounds"]["default"])

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
            strategy["loyalty"] = clamp("loyalty", strategy["loyalty"] + _cfg()["alpha"] * _cfg()["reward_satisfied_purchase"])
            strategy["risk_tolerance"] = clamp("risk_tolerance",
                strategy["risk_tolerance"] + _cfg()["alpha"] * _cfg()["reward_satisfied_purchase"] * _cfg()["risk_reward_ratio"])
        else:
            # Churned → bad decision
            strategy["loyalty"] = clamp("loyalty", strategy["loyalty"] + _cfg()["alpha"] * _cfg()["penalty_churn"])
            strategy["risk_tolerance"] = clamp("risk_tolerance",
                strategy["risk_tolerance"] + _cfg()["alpha"] * _cfg()["penalty_churn"] * _cfg()["risk_reward_ratio"])

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
                        if est_price > 0 and price_paid > est_price * _cfg()["overpaid_threshold_multiplier"]:
                            strategy["price_sensitivity"] = clamp("price_sensitivity",
                                strategy["price_sensitivity"] + _cfg()["alpha"] * _cfg()["overpaid_price_sensitivity_boost"])
                    except (ValueError, IndexError):
                        pass

    # ---- Reward signal 3: Social recommendation effectiveness ----
    my_recommendations = [h for h in history[-_cfg()["recommend_check_rounds"]:] if h.get("action") == "recommend"]
    if my_recommendations:
        # Check if any recommended peers later purchased
        rec_product = my_recommendations[-1].get("product_id")
        if rec_product:
            for conn_id in profile.get("social_network", {}).get("connections", []):
                if conn_id in agent_states:
                    conn_hist = agent_states[conn_id].get("history", [])
                    conn_bought = any(
                        h.get("action") == "purchase" and h.get("product_id") == rec_product
                        for h in conn_hist[-_cfg()["peer_purchase_check_rounds"]:]
                    )
                    if conn_bought:
                        strategy["social_susceptibility"] = clamp("social_susceptibility",
                            strategy["social_susceptibility"] + _cfg()["alpha"] * _cfg()["reward_recommendation_match"])

    # ---- Reward signal 4: Missed trends (FOMO learning) ----
    trending = market_signals.get("trending_products", [])
    if trending:
        my_purchases = set(purchased.keys())
        missed = set(trending) - my_purchases
        if missed:
            # Agent missed trending products → slightly increase early adopter tendency
            strategy["early_adopter"] = clamp("early_adopter",
                strategy["early_adopter"] + _cfg()["alpha"] * abs(_cfg()["penalty_missed_trend"]) * _cfg()["risk_reward_ratio"])

    # ---- Reward signal 5: Market sentiment alignment ----
    sentiment = market_signals.get("avg_sentiment", 0)
    if sentiment > _cfg()["sentiment_optimistic_threshold"] and not purchased:
        # Market is optimistic but agent hasn't bought → increase risk tolerance slightly
        strategy["risk_tolerance"] = clamp("risk_tolerance",
            strategy["risk_tolerance"] + _cfg()["alpha"] * 0.03)
    elif sentiment < _cfg()["sentiment_pessimistic_threshold"] and purchased:
        # Market is pessimistic but agent bought → decrease risk tolerance
        strategy["risk_tolerance"] = clamp("risk_tolerance",
            strategy["risk_tolerance"] + _cfg()["alpha"] * -0.03)

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
                if abs(delta) > _cfg()["strategy_shift_epsilon"]:
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
    if ps > _cfg()["behavior_thresholds"]["price_sensitive_high"]:
        lines.append("You are price-sensitive. Prefer cheaper options.")
    elif ps < _cfg()["behavior_thresholds"]["price_sensitive_low"]:
        lines.append("Price is not your main concern. Value quality over cost.")

    ea = strategy["early_adopter"]
    if ea > _cfg()["behavior_thresholds"]["early_adopter_high"]:
        lines.append("You are an early adopter. New products excite you.")
    elif ea < _cfg()["behavior_thresholds"]["early_adopter_low"]:
        lines.append("You prefer proven products. Avoid unvalidated new offerings.")

    ss = strategy["social_susceptibility"]
    if ss > _cfg()["behavior_thresholds"]["social_susceptible_high"]:
        lines.append("Peer opinions strongly influence your decisions.")
    elif ss < _cfg()["behavior_thresholds"]["social_susceptible_low"]:
        lines.append("You make independent decisions. Peer behavior doesn't sway you.")

    lo = strategy["loyalty"]
    if lo > _cfg()["behavior_thresholds"]["loyal_high"]:
        lines.append("Once you buy, you stick with it. Low churn risk.")
    elif lo < _cfg()["behavior_thresholds"]["loyal_low"]:
        lines.append("You churn easily if unsatisfied.")

    rt = strategy["risk_tolerance"]
    if rt > _cfg()["behavior_thresholds"]["risk_tolerant_high"]:
        lines.append("You take risks on unproven products.")
    elif rt < _cfg()["behavior_thresholds"]["risk_tolerant_low"]:
        lines.append("You are risk-averse. Only buy safe bets.")

    return " | ".join(lines) if lines else ""
