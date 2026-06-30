"""
Stage 4: Market Simulation Engine — Parallelized for multi-LLM speed.
30 rounds. Heterogeneous agents. Batch-parallel LLM calls within each round.
With progress logging + small-world network topology (UChicago 2025).

v4 changes:
- Cross-domain coupling (EconSimulacra 2026): 消费↔社交↔情绪联动 after each round
- Economic alignment RL (Agent Bazaar 2026): strategy adaptation from market outcomes
- RL strategy context injected into agent decision prompts
"""

import json, time, os, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from engine.config import simulation_cfg as _cfg, pipeline_cfg as _pcfg
from engine.llm_client import get_llm
from engine.coupling import apply_coupling, compute_fomo_boost, adjust_willingness_to_pay
from engine.alignment_rl import update_all_strategies, get_strategy_context_for_decision


def _safe_float(v, default=0.0):
    """Convert LLM output to float, handling strings and None."""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default

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
    if agent_type == "competitor" and round_num < _cfg()["competitor_activate_round"]:
        return {"agent_id": agent_id, "round": round_num, "action": "skip", "reason": "competitor_not_active_yet"}
    if agent_type == "environment" and round_num % _cfg()["environment_period"] != 0:
        return {"agent_id": agent_id, "round": round_num, "action": "skip", "reason": "environment_periodic"}

    # Build RL strategy context for decision prompt injection
    rl_context = get_strategy_context_for_decision(agent_id, {agent_id: state})

    # Build coupling context
    coupling_ctx = state.get("coupling_context", {})
    market_sentiment = coupling_ctx.get("market_sentiment", 0)
    fomo_active = coupling_ctx.get("fomo_active", False)

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
        "available_products": [{k: p.get(k) for k in ["id", "name", "category", "estimated_pricing_cny"]} for p in products[:_cfg()["products_shown"]]],
        "market_conditions": {
            "sentiment": "optimistic" if market_sentiment > 0.2 else ("pessimistic" if market_sentiment < -0.2 else "neutral"),
            "fomo_active": fomo_active,
        },
    }

    # Inject RL strategy guidance into the user prompt
    user_extra = ""
    if rl_context:
        user_extra = f"\n\nYOUR LEARNED BEHAVIOR: {rl_context}"

    try:
        llm = get_llm()
        decision = llm.chat_json(
            system=DECISION_SYSTEM_PROMPT,
            user=f"Round {round_num}/{total_rounds}. You are a {agent_type}. Make ONE economic decision.\n{json.dumps(context, indent=2, ensure_ascii=False)[:_cfg()["context_max_chars"]]}{user_extra}",
            agent_type=agent_type,
            temperature=0.6,
        )
        return decision
    except Exception as e:
        return {"agent_id": agent_id, "round": round_num, "action": "error", "error": str(e)}


def simulate(agents: list, product_directions: list, rounds: int = None, market_type: str = "b2c") -> dict:
    """Run 30-round market simulation with parallel agent decisions, coupling, and RL."""
    if rounds is None:
        rounds = _cfg()["rounds"]

    # Apply random seed for reproducibility (also set by pipeline entry, but we are callable standalone)
    seed_val = _cfg().get("random_seed", 42)
    if seed_val:
        random.seed(seed_val)
    # Cap agents for speed — use more with batch generation
    consumer_agents = [a for a in agents if a.get("type") == "consumer"][:_pcfg()["agent_consumer_cap"]]
    other_agents = [a for a in agents if a.get("type") != "consumer"]
    selected_agents = consumer_agents + other_agents

    # Initialize state
    agent_states = {}
    for a in selected_agents:
        agent_states[a["id"]] = {
            "profile": a, "history": [], "discovered_products": set(),
            "purchased_products": {}, "total_spent": 0, "emotional_state": "neutral",
            "recommendations_received": [],
            "rl_strategy": None,     # Initialized by alignment_rl on first update
            "coupling_context": {},  # Set by coupling engine each round
        }

    log, timeline = [], []
    coupling_history = []
    rl_history = []
    batch_size = _cfg()["batch_size"]  # More parallel workers for larger agent count
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
                    decision = future.result(timeout=_cfg()["agent_timeout"])
                except Exception:
                    decision = {"agent_id": aid, "round": rnd, "action": "timeout"}

                # Update agent state
                state = agent_states[aid]
                pid = decision.get("product_id")
                action = decision.get("action", "ignore")

                # Apply coupling adjustments
                emotional_state = decision.get("emotional_state", state["emotional_state"])
                base_wtp = _safe_float(decision.get("willingness_to_pay_cny", 0))

                # FOMO boost
                if pid and action in ("evaluate", "discover"):
                    fomo = compute_fomo_boost(aid, agent_states, pid)
                    if fomo > 0 and random.random() < fomo:
                        # FOMO triggers: upgrade evaluation to purchase
                        decision["action"] = "purchase"
                        decision["reasoning"] = f"{decision.get('reasoning', '')} (FOMO: peers bought)"

                # Emotion-adjusted willingness to pay
                if action == "purchase":
                    decision["willingness_to_pay_cny"] = adjust_willingness_to_pay(emotional_state, base_wtp)

                if action == "discover" and pid:
                    state["discovered_products"].add(pid)
                if action == "purchase" and pid:
                    wtp = _safe_float(decision.get("willingness_to_pay_cny", 0))
                    state["purchased_products"][pid] = {"round": rnd, "price_paid": wtp}
                    state["total_spent"] += wtp
                if action == "churn" and pid and pid in state["purchased_products"]:
                    state["purchased_products"][pid]["churned_at"] = rnd
                if action == "recommend" and pid:
                    for conn_id in state["profile"].get("social_network", {}).get("connections", [])[:5]:
                        if conn_id in agent_states:
                            agent_states[conn_id]["recommendations_received"].append({"from": aid, "product": pid, "round": rnd})

                state["emotional_state"] = emotional_state
                state["history"].append(decision)
                log.append(decision)

        # ---- Post-round: Cross-Domain Coupling (EconSimulacra 2026) ----
        coupling_stats = apply_coupling(agent_states, rnd, product_directions)
        coupling_history.append(coupling_stats)

        # ---- Post-round: Economic Alignment RL (Agent Bazaar 2026) ----
        market = coupling_stats.get("market_signals", {})
        rl_stats = update_all_strategies(agent_states, market, product_directions)
        rl_history.append(rl_stats)

        elapsed = time.time() - rnd_start
        errs = sum(1 for a in log[-len(agent_ids):] if a.get("action") in ("error", "timeout"))
        timeline.append({
            "round": rnd, "agents": len(agent_ids), "errors": errs,
            "sec": round(elapsed, 1),
            "market_sentiment": market.get("avg_sentiment", 0),
            "adoption_rate": market.get("adoption_rate", 0),
        })

        # Progress log every 5 rounds
        if rnd % _cfg()["log_interval"] == 0:
            total_elapsed = time.time() - started
            purchasers = sum(1 for s in agent_states.values() if s["purchased_products"])
            n_strats = sum(1 for s in agent_states.values() if s.get("rl_strategy"))
            print(f"  [SIM] Round {rnd}/{rounds} | {purchasers} purchasers | sentiment={market.get('avg_sentiment',0):.2f} | {n_strats} RL-active | {total_elapsed:.0f}s total", flush=True)

    results = _compute_results(agent_states, product_directions)

    # Collect final RL strategy summary
    final_strategies = {}
    for aid, state in agent_states.items():
        if state.get("rl_strategy"):
            final_strategies[aid] = state["rl_strategy"]

    return {
        "market_type": market_type,
        "rounds": rounds,
        "agent_count": len(selected_agents),
        "timeline": timeline,
        "log": log,
        "results": results,
        "coupling_history": coupling_history,
        "rl_summary": {
            "rounds_with_updates": len([r for r in rl_history if r.get("strategies_with_changes", 0) > 0]),
            "final_strategies_count": len(final_strategies),
            "avg_final_strategies": _avg_strategies(final_strategies) if final_strategies else {},
        },
    }


def _avg_strategies(strategies: dict) -> dict:
    """Compute average strategy values across all agents."""
    if not strategies:
        return {}
    keys = ["price_sensitivity", "early_adopter", "social_susceptibility", "loyalty", "risk_tolerance"]
    avgs = {}
    for key in keys:
        vals = [s[key] for s in strategies.values() if key in s]
        avgs[key] = round(sum(vals) / len(vals), 3) if vals else 0
    return avgs


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
        churned = sum(1 for aid in purchasers if "churned_at" in agent_states[aid]["purchased_products"].get(pid, {}))
        # Zero buyers → zero retention score (nothing to measure)
        if pc == 0:
            churn_r = 0.0
            retention_term = 0.0
        else:
            churn_r = churned / pc
            retention_term = (1 - churn_r) * _cfg()["score_retention_weight"]
        revenue = sum(_safe_float(st["purchased_products"].get(pid, {}).get("price_paid", 0)) for st in agent_states.values())
        adoption = pc / max(1, total_agents * _cfg()["score_adoption_denominator"])
        adoption_term = adoption * _cfg()["score_adoption_weight"]
        revenue_norm = min(revenue / max(pc * _cfg()["score_revenue_per_user_baseline"], 1), 1.0)
        revenue_term = revenue_norm * _cfg()["score_revenue_weight"]
        score = adoption_term + retention_term + revenue_term
        results.append({"product_id": pid, "product_name": p.get("name", ""), "purchasers": pc,
                        "churn_rate": round(churn_r, 2), "total_revenue_cny": revenue,
                        "survival_score": round(min(1.0, score), 3),
                        "status": "alive" if score > _cfg()["alive_threshold"] else ("struggling" if score > _cfg()["struggling_threshold"] else "dead")})
    results.sort(key=lambda r: r["survival_score"], reverse=True)
    return results
