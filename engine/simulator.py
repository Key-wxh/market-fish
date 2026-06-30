"""
Stage 4: Market Simulation Engine — Parallelized for multi-LLM speed.
30 rounds. Heterogeneous agents. Batch-parallel LLM calls within each round.
With progress logging + small-world network topology (UChicago 2025).

v3 changes:
- ThreadPoolExecutor parallel agent decisions per round (batch size 10)
- Fast models only for simulation (DeepSeek/Qwen), slow models for reports
- Agent cap: 30 B2C max for speed
- Round-by-round progress logging
"""

import json, time, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from engine.llm_client import get_llm

DECISION_SYSTEM_PROMPT = """You are a market agent making a real economic decision. You have a specific identity, budget, pain points.

Based on your current state and the market conditions, decide ONE action this round.
Output JSON: {"agent_id":"id","round":0,"action":"discover|evaluate|purchase|renew|churn|recommend|ignore","product_id":"id or null","confidence":0.0-1.0,"reasoning":"one sentence","willingness_to_pay_cny":0,"will_recommend":false,"emotional_state":"excited|curious|skeptical|indifferent|frustrated|satisfied"}
Budget is a HARD constraint. Cannot spend more than budget_monthly_cny.
After discovering: if product solves pain→purchase. If not→ignore. After purchase: if satisfied→renew. If not→churn."""


def _decide_one_agent(agent_id: str, state: dict, round_num: int, products: list, total_rounds: int) -> dict:
    """Single agent decision — called in parallel within each round."""
    profile = state["profile"]
    agent_type = profile.get("type", "consumer")

    # Skip logic
    if agent_type == "competitor" and round_num < 8:
        return {"agent_id": agent_id, "round": round_num, "action": "skip", "reason": "competitor_not_active_yet"}
    if agent_type == "environment" and round_num % 5 != 0:
        return {"agent_id": agent_id, "round": round_num, "action": "skip", "reason": "environment_periodic"}

    context = {
        "agent_profile": {k: v for k, v in profile.items() if k != "bdi"},
        "bdi": profile.get("bdi", {}),
        "current_state": {
            "discovered": list(state["discovered_products"]),
            "purchased": {k: {"round": v["round"]} for k, v in state["purchased_products"].items()},
            "total_spent": state["total_spent"],
            "emotional": state["emotional_state"],
        },
        "round": round_num,
        "available_products": [{k: p.get(k) for k in ["id", "name", "category", "estimated_pricing_cny"]} for p in products[:3]],
    }

    try:
        llm = get_llm()
        decision = llm.chat_json(
            system=DECISION_SYSTEM_PROMPT,
            user=f"Round {round_num}/{total_rounds}. You are a {agent_type}. Make ONE economic decision.\n{json.dumps(context, indent=2, ensure_ascii=False)[:3000]}",
            agent_type=agent_type,
            temperature=0.6,
        )
        return decision
    except Exception as e:
        return {"agent_id": agent_id, "round": round_num, "action": "error", "error": str(e)}


def simulate(agents: list, product_directions: list, rounds: int = 30, market_type: str = "b2c") -> dict:
    """Run 30-round market simulation with parallel agent decisions."""
    # Cap agents for speed
    consumer_agents = [a for a in agents if a.get("type") == "consumer"][:30]
    other_agents = [a for a in agents if a.get("type") != "consumer"]
    selected_agents = consumer_agents + other_agents

    # Initialize state
    agent_states = {}
    for a in selected_agents:
        agent_states[a["id"]] = {
            "profile": a, "history": [], "discovered_products": set(),
            "purchased_products": {}, "total_spent": 0, "emotional_state": "neutral",
            "recommendations_received": [],
        }

    log, timeline = [], []
    batch_size = 10
    started = time.time()

    for rnd in range(1, rounds + 1):
        rnd_start = time.time()
        agent_ids = list(agent_states.keys())

        # Parallel batch execution
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(_decide_one_agent, aid, agent_states[aid], rnd, product_directions, rounds): aid
                for aid in agent_ids
            }
            for future in as_completed(futures):
                aid = futures[future]
                try:
                    decision = future.result(timeout=30)
                except Exception:
                    decision = {"agent_id": aid, "round": rnd, "action": "timeout"}

                # Update agent state
                state = agent_states[aid]
                pid = decision.get("product_id")
                action = decision.get("action", "ignore")

                if action == "discover" and pid:
                    state["discovered_products"].add(pid)
                if action == "purchase" and pid:
                    state["purchased_products"][pid] = {"round": rnd, "price_paid": decision.get("willingness_to_pay_cny", 0)}
                    state["total_spent"] += decision.get("willingness_to_pay_cny", 0)
                if action == "churn" and pid and pid in state["purchased_products"]:
                    state["purchased_products"][pid]["churned_at"] = rnd
                if action == "recommend" and pid:
                    for conn_id in state["profile"].get("social_network", {}).get("connections", [])[:5]:
                        if conn_id in agent_states:
                            agent_states[conn_id]["recommendations_received"].append({"from": aid, "product": pid, "round": rnd})

                state["emotional_state"] = decision.get("emotional_state", "neutral")
                state["history"].append(decision)
                log.append(decision)

        elapsed = time.time() - rnd_start
        errs = sum(1 for a in log[-len(agent_ids):] if a.get("action") in ("error", "timeout"))
        timeline.append({"round": rnd, "agents": len(agent_ids), "errors": errs, "sec": round(elapsed, 1)})

        # Progress log every 5 rounds
        if rnd % 5 == 0:
            total_elapsed = time.time() - started
            purchasers = sum(1 for s in agent_states.values() if s["purchased_products"])
            print(f"  [SIM] Round {rnd}/{rounds} | {purchasers} purchasers | {errs} errs | {total_elapsed:.0f}s total", flush=True)

    results = _compute_results(agent_states, product_directions)
    return {"market_type": market_type, "rounds": rounds, "agent_count": len(selected_agents),
            "timeline": timeline, "log": log, "results": results}


def _compute_results(agent_states: dict, products: list) -> list:
    results = []
    total_agents = max(len(agent_states), 1)
    for i, p in enumerate(products):
        pid = p.get("id", f"prod-{i}")
        purchasers = []
        for aid, st in agent_states.items():
            if pid in st["purchased_products"]:
                purchasers.append(aid)
        pc = len(purchasers)
        churned = sum(1 for aid in purchasers if "churned_at" in st["purchased_products"].get(pid, {}))
        churn_r = churned / pc if pc > 0 else 1.0
        revenue = sum(st["purchased_products"].get(pid, {}).get("price_paid", 0) for st in agent_states.values())
        score = (pc / max(1, total_agents * 0.1)) * 0.4 + ((1 - churn_r) * 0.3) + (min(revenue / max(pc * 50, 1), 1.0) * 0.3)
        results.append({"product_id": pid, "product_name": p.get("name", ""), "purchasers": pc,
                        "churn_rate": round(churn_r, 2), "total_revenue_cny": revenue,
                        "survival_score": round(min(1.0, score), 3),
                        "status": "alive" if score > 0.3 else ("struggling" if score > 0.1 else "dead")})
    results.sort(key=lambda r: r["survival_score"], reverse=True)
    return results
