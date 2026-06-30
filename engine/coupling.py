"""
Cross-Domain Coupling Engine — EconSimulacra 2026 principle.
消费 ↔ 社交 ↔ 情绪 三域联动

Key findings from EconSimulacra (arXiv 2026):
- Real markets exhibit cross-domain coupling: consumption decisions affect emotions,
  emotions affect social sharing, social sharing affects consumption.
- Pure domain isolation misses emergent behaviors: fads, panics, network effects.
- Negative emotions spread 2x faster than positive (negativity bias).
- FOMO (fear of missing out) creates non-linear adoption curves.

Implementation:
1. Emotion → WillingnessToPay mapping: excited +30%, frustrated -50%
2. Social contagion: emotions propagate through small-world network each round
3. FOMO effect: seeing 3+ peers buy → +25% purchase probability
4. Negativity bias: negative sentiment spreads at 2x rate through network
5. Market-level coupling: aggregate sentiment affects all agents (macro→micro)
"""

import random
import math
from engine.config import coupling_cfg as _cfg

def _C(key, default=None):
    return _cfg().get(key, default)


def _emotion_valence(emotion: str) -> float:
    """Map emotion to valence score (-1.0 to +1.0)."""
    return _cfg()["emotion_valence"].get(emotion, 0.0)


def _valence_to_emotion(valence: float) -> str:
    """Map valence score back to emotion string using config thresholds."""
    for threshold, emotion in _cfg()["valence_thresholds"]:
        if valence > threshold:
            return emotion
    return "frustrated"


def compute_market_signals(agent_states: dict) -> dict:
    """
    Compute aggregate market signals from all agent states.
    These macro signals affect micro (individual) agent behavior.
    """
    n = len(agent_states)
    if n == 0:
        return {"avg_sentiment": 0.0, "adoption_rate": 0.0, "trending_products": [],
                "churn_rate": 0.0, "active_purchasers": 0}

    # Average sentiment
    valences = [_emotion_valence(s["emotional_state"]) for s in agent_states.values()]
    avg_valence = sum(valences) / n

    # Adoption rate: % of agents who have purchased at least one product
    purchasers = sum(1 for s in agent_states.values() if s["purchased_products"])
    adoption_rate = purchasers / n

    # Trending products: products with most recent purchases
    from collections import Counter
    lookback = _cfg()["trending_lookback_rounds"]
    recent_purchases = Counter()
    for s in agent_states.values():
        for h in s["history"][-lookback:]:
            pid = h.get("product_id")
            if pid and h.get("action") == "purchase":
                recent_purchases[pid] += 1

    top_n = _cfg()["trending_top_n"]
    min_count = _cfg()["trending_min_count"]
    trending = [pid for pid, count in recent_purchases.most_common(top_n) if count >= min_count]

    # Churn rate
    total_purchases = sum(len(s["purchased_products"]) for s in agent_states.values())
    churned = sum(
        1 for s in agent_states.values()
        for p in s["purchased_products"].values()
        if "churned_at" in p
    )
    churn_rate = churned / max(total_purchases, 1)

    return {
        "avg_sentiment": round(avg_valence, 3),
        "adoption_rate": round(adoption_rate, 3),
        "trending_products": trending,
        "churn_rate": round(churn_rate, 3),
        "active_purchasers": purchasers,
    }


def propagate_emotions(agent_states: dict) -> dict:
    """
    Propagate emotions through the small-world social network.

    Rules:
    - Each agent's emotion is influenced by their connected peers' emotions
    - Negative emotions spread 2x faster (negativity bias)
    - Agents with high influence_weight affect others more
    - Each agent also regresses toward the market average sentiment (macro→micro coupling)

    Returns updated agent_states (mutated in place, also returned for convenience).
    """
    if not agent_states:
        return agent_states

    # Compute market signal first
    market = compute_market_signals(agent_states)

    # Snapshot current emotions
    current_emotions = {
        aid: _emotion_valence(s["emotional_state"])
        for aid, s in agent_states.items()
    }

    new_emotions = {}
    for aid, state in agent_states.items():
        profile = state.get("profile", {})
        social = profile.get("social_network", {})
        connections = social.get("connections", [])
        influence_weight = profile.get("influence_weight", 1.0)

        if not connections:
            # Isolated agent: just regress toward market mean
            own_valence = current_emotions[aid]
            new_valence = own_valence * (1 - _cfg()["market_sentiment_weight"]) + market["avg_sentiment"] * _cfg()["market_sentiment_weight"]
            new_emotions[aid] = new_valence
            continue

        # Compute social influence from connected peers
        peer_valences = []
        for conn_id in connections:
            if conn_id in current_emotions:
                conn_valence = current_emotions[conn_id]
                # Negativity bias: negative emotions exert stronger influence
                if conn_valence < 0:
                    conn_valence *= _cfg()["negativity_spread_multiplier"]
                peer_valences.append(conn_valence)

        if not peer_valences:
            new_emotions[aid] = current_emotions[aid]
            continue

        avg_peer_valence = sum(peer_valences) / len(peer_valences)

        # Own susceptibility: higher influence_weight = less susceptible to others
        susceptibility = max(_cfg()["min_susceptibility"], 1.0 - influence_weight * _cfg()["influence_susceptibility_factor"])
        social_influence = avg_peer_valence * _cfg()["contagion_strength"] * susceptibility

        # Macro influence: all agents slightly pulled toward market average
        macro_influence = market["avg_sentiment"] * _cfg()["market_sentiment_weight"]

        # Compute new valence: own + social + macro, clamped to [-1, 1]
        own_valence = current_emotions[aid]
        new_valence = own_valence * (1 - _cfg()["contagion_strength"] * susceptibility - _cfg()["market_sentiment_weight"])
        new_valence += social_influence + macro_influence
        new_valence = max(-1.0, min(1.0, new_valence))

        new_emotions[aid] = new_valence

    # Apply new emotions back to agent states
    for aid, valence in new_emotions.items():
        agent_states[aid]["emotional_state"] = _valence_to_emotion(valence)

    return agent_states


def compute_fomo_boost(agent_id: str, agent_states: dict, product_id: str) -> float:
    """
    Compute FOMO (Fear Of Missing Out) purchase probability boost.

    If 3+ connected peers have purchased a product, the agent gets a +25% boost
    to purchase probability for that product.

    Returns 0.0 to _cfg()["fomo_purchase_boost"].
    """
    state = agent_states.get(agent_id)
    if not state:
        return 0.0

    profile = state.get("profile", {})
    social = profile.get("social_network", {})
    connections = social.get("connections", [])

    if not connections:
        return 0.0

    # Count connected peers who purchased this product
    peer_purchasers = 0
    for conn_id in connections:
        if conn_id in agent_states:
            conn_state = agent_states[conn_id]
            if product_id in conn_state["purchased_products"]:
                peer_purchasers += 1

    if peer_purchasers >= _cfg()["fomo_peer_threshold"]:
        return _cfg()["fomo_purchase_boost"]

    # Partial FOMO: 1-2 peers = smaller boost
    if peer_purchasers >= 2:
        return _cfg()["fomo_purchase_boost"] * _cfg()["fomo_partial_2_peers"]
    if peer_purchasers >= 1:
        return _cfg()["fomo_purchase_boost"] * _cfg()["fomo_partial_1_peer"]

    return 0.0


def adjust_willingness_to_pay(emotional_state: str, base_wtp: float) -> float:
    """
    Adjust willingness-to-pay based on emotional state.

    Excited agents pay more, frustrated agents pay much less.
    This is the 消费↔情绪 coupling direction.
    """
    multiplier = _cfg()["emotion_wtp_multiplier"].get(emotional_state, 1.0)
    return round(base_wtp * multiplier, 2)


def apply_coupling(agent_states: dict, current_round: int, product_directions: list) -> dict:
    """
    Main coupling update — called after each simulation round.

    Updates in order:
    1. Propagate emotions through social network (社交→情绪)
    2. Compute market signals for next round (消费+情绪→市场信号)

    Returns coupling_stats for logging.
    """
    # Step 1: Emotion propagation through social network
    agent_states = propagate_emotions(agent_states)

    # Step 2: Compute market signals
    market = compute_market_signals(agent_states)

    # Step 3: Update each agent's purchase context with FOMO and market awareness
    for aid, state in agent_states.items():
        state["coupling_context"] = {
            "round": current_round,
            "market_sentiment": market["avg_sentiment"],
            "adoption_rate": market["adoption_rate"],
            "trending_products": market["trending_products"],
            "fomo_active": market["adoption_rate"] > _cfg()["fomo_activation_adoption_rate"],
        }

    return {
        "round": current_round,
        "market_signals": market,
        "emotions_propagated": True,
    }
