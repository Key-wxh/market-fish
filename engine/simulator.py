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
from engine.config import simulation_cfg as _cfg, pipeline_cfg as _pcfg, get_config
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


def _decide_one_agent(agent_id: str, state: dict, round_num: int, products: list, total_rounds: int,
                      memory_context: str = "") -> dict:
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

    # v6: BDI v2 cognitive context
    bdi_context = ""
    if get_config().get("bdi_v2", {}).get("enabled", False):
        from engine.bdi_v2 import bdi_decision_context
        bdi_context = bdi_decision_context(profile, state, round_num, products, market_sentiment)

    # v6: Grounding RAG context
    rag_ctx = ""
    if get_config().get("grounding", {}).get("enabled", False):
        from engine.grounding import rag_context
        rag_ctx = rag_context(profile, products, state.get("_seed_data"))

    # Inject RL strategy guidance + v6 contexts into the user prompt
    user_extra = ""
    if bdi_context:
        user_extra += bdi_context
    if rl_context:
        user_extra += f"\n\nYOUR LEARNED BEHAVIOR: {rl_context}"
    if rag_ctx:
        user_extra += rag_ctx
    if memory_context:
        user_extra += memory_context

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
    batch_size = _cfg()["batch_size"]

    # v6: Memory module (Generative Agents 2023)
    mem_cfg = get_config().get("memory", {})
    memory_enabled = mem_cfg.get("enabled", False)
    memory_streams = {}
    if memory_enabled:
        from engine.memory import MemoryStream, inject_memories_to_context, record_decision_memory
        for aid in agent_states:
            memory_streams[aid] = MemoryStream(
                agent_id=aid,
                capacity=mem_cfg.get("capacity", 1000),
                reflection_interval=mem_cfg.get("reflection_interval", 10),
                recency_weight=mem_cfg.get("retrieval_recency_weight", 0.6),
                relevance_weight=mem_cfg.get("retrieval_relevance_weight", 0.3),
                importance_weight=mem_cfg.get("retrieval_importance_weight", 0.1),
                reflection_top_k=mem_cfg.get("reflection_top_k", 3),
            )
        print(f"  [MEMORY] Initialized for {len(memory_streams)} agents", flush=True)
    started = time.time()

    for rnd in range(1, rounds + 1):
        rnd_start = time.time()
        agent_ids = list(agent_states.keys())

        # v6: Temporal activation (OASIS) — only activate a subset
        temporal_cfg = get_config().get("temporal", {})
        if temporal_cfg.get("enabled", False):
            from engine.temporal import activate_agents
            active_ids, inactive_ids = activate_agents(agent_ids, rnd, rounds)
        else:
            active_ids, inactive_ids = agent_ids, []

        # v6: RecSys filter (OASIS) — personalized product recommendations
        recsys_cfg = get_config().get("recsys", {})
        if recsys_cfg.get("enabled", False):
            from engine.recsys import recsys_filter
            profiles = {aid: agent_states[aid]["profile"] for aid in active_ids}
            recs = recsys_filter(product_directions, profiles, rnd)
        else:
            recs = {aid: product_directions for aid in active_ids}

        # v6: Stress computation (EconSimulacra)
        stress_cfg = get_config().get("stress", {})
        if stress_cfg.get("enabled", False):
            from engine.stress import apply_stress
            apply_stress(agent_states, {})

        # v6: Memory retrieval before decisions
        mem_contexts = {}
        if memory_enabled:
            product_names = ", ".join(p.get("name", p.get("id", "")) for p in product_directions[:3])
            query = f"round {rnd} evaluating: {product_names[:200]}"
            for aid in active_ids:
                mem_contexts[aid] = inject_memories_to_context(aid, query, memory_streams, top_k=3)

        # Parallel batch execution (active agents only)
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(_decide_one_agent, aid, agent_states[aid], rnd,
                                recs.get(aid, product_directions), rounds,
                                mem_contexts.get(aid, "")): aid
                for aid in active_ids
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

                # v6: Grounding validation
                if get_config().get("grounding", {}).get("enabled", False):
                    from engine.grounding import ground_validate
                    decision = ground_validate(decision, state["profile"], state.get("_seed_data"))

                # v6: BDI intention update (TwinMarket Step 6)
                if get_config().get("bdi_v2", {}).get("enabled", False):
                    from engine.bdi_v2 import update_bdi_intentions
                    update_bdi_intentions(aid, state, decision, rnd)

                # v6: Stress-adjusted WTP
                if stress_cfg.get("enabled", False):
                    from engine.stress import stress_to_wtp_multiplier
                    sl = state.get("stress_level", 0)
                    if action == "purchase":
                        multiplier = stress_to_wtp_multiplier(sl)
                        decision["willingness_to_pay_cny"] = round(
                            _safe_float(decision.get("willingness_to_pay_cny", 0)) * multiplier, 1)

                # v6: Record decision as memory
                if memory_enabled and action not in ("skip", "error", "timeout"):
                    try:
                        record_decision_memory(aid, decision, rnd, task_id=market_type, memory_streams=memory_streams)
                    except Exception:
                        pass

        # v6: Inactive agents receive passive updates (social/emotional only)
        for aid in inactive_ids:
            state = agent_states[aid]
            state["history"].append({"agent_id": aid, "round": rnd, "action": "inactive",
                                     "reason": "temporal_deactivation"})
            log.append(state["history"][-1])

        # ---- Post-round: Memory Reflection (Generative Agents 2023) ----
        if memory_enabled and rnd % memory_streams[list(agent_ids)[0]].reflection_interval == 0:
            reflected = 0
            for aid in agent_ids:
                try:
                    mems = memory_streams[aid].reflect()
                    reflected += len(mems)
                except Exception:
                    pass
            if reflected > 0:
                print(f"  [MEMORY] Round {rnd}: {reflected} reflections generated", flush=True)

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

    # v6: Memory consolidation at simulation end
    if memory_enabled:
        total_removed = 0
        for aid in agent_ids:
            try:
                total_removed += memory_streams[aid].consolidate()
            except Exception:
                pass
        mem_stats = {aid: memory_streams[aid].stats()["total"] for aid in list(agent_ids)[:5]}
        print(f"  [MEMORY] Consolidated: {total_removed} removed, sample sizes: {mem_stats}", flush=True)

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
        "agent_states": agent_states,  # v6: for persistence after simulation
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
