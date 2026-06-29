"""
Stage 4: Market Simulation Engine.
30 rounds. BDI agent decisions. IPC subprocess architecture (MiroFish pattern).
3 markets at 3 speeds: B2C (1 day/round), SMB (1 week/round), Enterprise (2 weeks/round).

Design principles from academic papers:
- Heterogeneous LLMs for different agent types (Machine Spirits 2026)
- Small-world network topology for information spread (UChicago 2025)
- BDI cognitive architecture for realistic decisions (TwinMarket NeurIPS 2025)
- Cross-domain coupling: consumption ↔ social behavior ↔ sentiment (EconSimulacra 2026)
"""

import json
import time
import os
from datetime import datetime, timedelta
from engine.llm_client import get_llm

DECISION_SYSTEM_PROMPT = """You are a market agent making a real economic decision. You have a specific identity, budget, pain points, and social network.

Based on your current state and the market conditions, decide ONE action this round.

Output EXACTLY this JSON:
{
  "agent_id": "your_id",
  "round": 0,
  "action": "discover|evaluate|purchase|renew|churn|recommend|ignore|compete|adapt|exit",
  "product_id": "which product you are acting on (or null)",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence explaining your decision",
  "willingness_to_pay_cny": 0 or specific number,
  "will_recommend": true or false,
  "emotional_state": "excited|curious|skeptical|indifferent|frustrated|satisfied",
  "social_signal": "what you heard from your network this round (or null)"
}

RULES:
- Base your decision on your BDI (Beliefs, Desires, Intentions) and current market state.
- If you haven't discovered the product yet, you can't evaluate or buy it.
- Budget is a HARD constraint. Cannot spend more than your budget_monthly_cny.
- Emotional state affects decision: excited → impulse buy, skeptical → need more social proof, indifferent → ignore.
- Social network matters: if someone in your network recommended it, discovery chance increases.
- After purchasing: if product solves your pain → renew. If not → churn.
"""


def simulate(
    agents: list[dict],
    product_directions: list[dict],
    rounds: int = 30,
    market_type: str = "b2c",
) -> dict:
    """
    Run 30-round market simulation.

    Args:
        agents: Agent definitions from agent_factory
        product_directions: Product ideas to test
        rounds: Number of simulation rounds
        market_type: "b2c" | "smb" | "enterprise" (controls round speed)
    """
    llm = get_llm()

    # Round duration based on market type
    round_durations = {"b2c": "1 day", "smb": "1 week", "enterprise": "2 weeks"}
    round_label = round_durations.get(market_type, "1 week")

    # Initialize agent states
    agent_states = {}
    for a in agents:
        agent_states[a["id"]] = {
            "profile": a,
            "history": [],
            "discovered_products": set(),
            "purchased_products": {},
            "total_spent": 0,
            "emotional_state": "neutral",
            "recommendations_received": [],
        }

    # Simulation log
    log = []
    timeline = []

    for round_num in range(1, rounds + 1):
        round_start = time.time()
        round_actions = []

        # Each agent makes ONE decision this round
        for agent_id, state in agent_states.items():
            profile = state["profile"]
            agent_type = profile.get("type", "consumer")

            # Skip environment/competitor agents in early rounds (they activate later)
            if agent_type == "competitor" and round_num < 10:
                continue
            if agent_type == "environment" and round_num % 5 != 0:
                continue

            try:
                # Build decision context
                context = {
                    "agent_profile": {k: v for k, v in profile.items() if k != "bdi"},
                    "bdi": profile.get("bdi", {}),
                    "current_state": {
                        "discovered_products": list(state["discovered_products"]),
                        "purchased": state["purchased_products"],
                        "total_spent": state["total_spent"],
                        "emotional_state": state["emotional_state"],
                        "recommendations_received": state["recommendations_received"][-5:],
                    },
                    "market_round": round_num,
                    "round_duration": round_label,
                    "available_products": [
                        {
                            "id": p.get("id", f"prod-{i}"),
                            "name": p.get("name", ""),
                            "category": p.get("category", ""),
                            "pricing_cny": p.get("estimated_pricing_cny", ""),
                            "target_market": p.get("target_market", ""),
                        }
                        for i, p in enumerate(product_directions)
                    ],
                }

                # LLM decision
                decision = llm.chat_json(
                    system=DECISION_SYSTEM_PROMPT,
                    user=f"Round {round_num}/{rounds}. Agent type: {agent_type}. Make ONE economic decision.\n\n{json.dumps(context, indent=2, ensure_ascii=False)}",
                )

                # Update agent state based on decision
                product_id = decision.get("product_id")
                action = decision.get("action", "ignore")

                if action == "discover" and product_id:
                    state["discovered_products"].add(product_id)

                if action == "purchase" and product_id:
                    wtp = decision.get("willingness_to_pay_cny", 0)
                    state["purchased_products"][product_id] = {
                        "round": round_num,
                        "price_paid": wtp,
                    }
                    state["total_spent"] += wtp

                if action == "churn" and product_id and product_id in state["purchased_products"]:
                    state["purchased_products"][product_id]["churned_at"] = round_num

                if action == "recommend" and product_id:
                    # Spread to connected agents via small-world network
                    connections = profile.get("social_network", {}).get("connections", [])
                    for conn_id in connections:
                        if conn_id in agent_states:
                            agent_states[conn_id]["recommendations_received"].append({
                                "from": agent_id,
                                "product": product_id,
                                "round": round_num,
                            })

                state["emotional_state"] = decision.get("emotional_state", "neutral")
                state["history"].append(decision)
                round_actions.append(decision)

            except Exception as e:
                # Agent timeout/failure: skip this round, continue
                round_actions.append({
                    "agent_id": agent_id,
                    "round": round_num,
                    "action": "error",
                    "error": str(e),
                })

        # Record round
        round_elapsed = time.time() - round_start
        timeline.append({
            "round": round_num,
            "actions": len(round_actions),
            "error_count": sum(1 for a in round_actions if a.get("action") == "error"),
            "elapsed_sec": round_elapsed,
        })
        log.extend(round_actions)

    # Compute survival metrics
    results = _compute_results(agent_states, product_directions, rounds)

    return {
        "market_type": market_type,
        "rounds": rounds,
        "round_duration": round_label,
        "agent_count": len(agents),
        "timeline": timeline,
        "log": log,
        "results": results,
    }


def _compute_results(agent_states: dict, products: list[dict], rounds: int) -> list[dict]:
    """Compute survival metrics for each product direction."""
    results = []

    for i, product in enumerate(products):
        pid = product.get("id", f"prod-{i}")

        # Count purchases, churns, recommendations
        purchasers = []
        churners = []
        recommenders = []
        total_revenue = 0

        for agent_id, state in agent_states.items():
            if pid in state["purchased_products"]:
                purchasers.append(agent_id)
                total_revenue += state["purchased_products"][pid].get("price_paid", 0)

                if "churned_at" in state["purchased_products"][pid]:
                    churners.append(agent_id)

            # Check if agent recommended this product
            for h in state.get("history", []):
                if h.get("action") == "recommend" and h.get("product_id") == pid:
                    recommenders.append(agent_id)
                    break

        purchaser_count = len(purchasers)
        churn_rate = len(churners) / purchaser_count if purchaser_count > 0 else 1.0
        recommend_rate = len(recommenders) / len(agent_states) if agent_states else 0

        # Survival score
        total_agents = max(len(agent_states), 1)
        survival_score = (
            (purchaser_count / max(1, total_agents * 0.1)) * 0.4 +          # Market penetration
            ((1 - churn_rate) * 0.3) +                                       # Retention
            (min(recommend_rate * 10, 1.0) * 0.2) +                          # Virality (capped)
            (min(total_revenue / max(purchaser_count * 100, 1), 1.0) * 0.1) # Revenue per user (capped)
        )
        survival_score = min(1.0, survival_score)

        results.append({
            "product_id": pid,
            "product_name": product.get("name", ""),
            "purchasers": purchaser_count,
            "churn_rate": round(churn_rate, 2),
            "recommenders": len(recommenders),
            "total_revenue_cny": total_revenue,
            "survival_score": round(survival_score, 3),
            "status": "alive" if survival_score > 0.3 else ("struggling" if survival_score > 0.1 else "dead"),
        })

    # Sort by survival score
    results.sort(key=lambda r: r["survival_score"], reverse=True)
    return results
