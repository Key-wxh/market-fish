"""
Evidence Report Generator — translates simulation data into readable product reports.
The value expression layer of MarketFish.

Data sources: agent reasoning, RL strategies, coupling history, purchase timeline.
"""

import json
from collections import Counter, defaultdict
from engine.i18n import t as _t


def extract_purchase_reasons(product_id: str, agent_states: dict, max_reasons: int = 5) -> list[dict]:
    """Extract purchase motivations from agent decision reasoning."""
    reasons = []
    for aid, state in agent_states.items():
        for h in state.get("history", []):
            if h.get("action") == "purchase" and h.get("product_id") == product_id:
                reasoning = h.get("reasoning", "")
                if reasoning:
                    reasons.append({
                        "agent_id": aid,
                        "round": h.get("round", 0),
                        "reasoning": reasoning,
                        "emotional_state": h.get("emotional_state", "neutral"),
                    })
    return reasons[:max_reasons * 3]  # Return all for aggregation, cap for display


def build_buyer_profile(product_id: str, agent_states: dict, agents: list) -> dict:
    """Cluster buyers by RL strategy dimensions."""
    buyers = []
    for aid, state in agent_states.items():
        if product_id in state.get("purchased_products", {}):
            profile = state.get("profile", {})
            atype = profile.get("type", "consumer")
            # Exclude competitor/environment agents from buyer profile (they aren't real consumers)
            if atype in ("competitor", "environment"):
                continue
            strategy = state.get("rl_strategy", {})
            buyers.append({
                "agent_id": aid,
                "type": profile.get("type", "consumer"),
                "budget": _safe_float(profile.get("budget_monthly_cny", 0)),
                "decision_speed": profile.get("decision_speed", "days"),
                "strategy": strategy,
            })

    if not buyers:
        return {"total_buyers": 0, "segments": []}

    # Cluster into segments based on strategy dimensions (with profile fallback)
    price_sensitive = [b for b in buyers if (
        b.get("strategy", {}).get("price_sensitivity", 0) > 0.6 or
        _safe_float(b.get("budget", 0)) < 300  # Low budget → price sensitive
    )]
    impulsive = [b for b in buyers if (
        b.get("decision_speed") == "impulse" or
        b.get("strategy", {}).get("early_adopter", 0) > 0.6
    )]
    rational = [b for b in buyers if (
        b.get("strategy", {}).get("social_susceptibility", 0) < 0.3 or
        b.get("decision_speed") in ("weeks", "months")
    )]
    # Remove overlap: an agent can only be in one segment (prioritize impulsive > price_sensitive > rational)
    impulsive_ids = {b["agent_id"] for b in impulsive}
    price_sensitive = [b for b in price_sensitive if b["agent_id"] not in impulsive_ids]
    rational_ids = {b["agent_id"] for b in impulsive + price_sensitive}
    rational = [b for b in rational if b["agent_id"] not in rational_ids]

    total = len(buyers)
    return {
        "total_buyers": total,
        "avg_budget": round(sum(b["budget"] for b in buyers) / total, 1) if total else 0,
        "segments": [
            {"name": _t("evidence_tab.price_sensitive_seg"), "count": len(price_sensitive), "pct": round(len(price_sensitive) / total * 100, 1),
             "description": _t("evidence_tab.price_sensitive_desc")},
            {"name": _t("evidence_tab.impulsive_seg"), "count": len(impulsive), "pct": round(len(impulsive) / total * 100, 1),
             "description": _t("evidence_tab.impulsive_desc")},
            {"name": _t("evidence_tab.rational_seg"), "count": len(rational), "pct": round(len(rational) / total * 100, 1),
             "description": _t("evidence_tab.rational_desc")},
        ],
    }


def detect_fomo_events(product_id: str, coupling_history: list) -> list[dict]:
    """Detect FOMO trigger points from coupling history."""
    events = []
    prev_purchasers = 0
    for entry in coupling_history:
        if not isinstance(entry, dict):
            continue
        signals = entry.get("market_signals", {})
        trending = signals.get("trending_products", [])
        if product_id in trending and signals.get("adoption_rate", 0) > 0.2:
            round_num = entry.get("round", 0)
            events.append({
                "round": round_num,
                "adoption_rate": signals.get("adoption_rate", 0),
                "sentiment": signals.get("avg_sentiment", 0),
                "description": f"第 {round_num} 轮 FOMO 触发：采纳率 {signals.get('adoption_rate', 0):.1%}，市场情绪 {signals.get('avg_sentiment', 0):.2f}",
            })
    return events[:5]


def compare_with_competitors(product_id: str, all_results: list) -> list[dict]:
    """Compare this product against competitors in the simulation."""
    competitors = []
    target_score = None
    for r in all_results:
        if not isinstance(r, dict):
            continue
        pid = r.get("product_id", "")
        if pid == product_id:
            target_score = r.get("survival_score", 0)
        else:
            competitors.append({
                "name": r.get("product_name", "?"),
                "score": r.get("survival_score", 0),
                "purchasers": r.get("purchasers", 0),
                "revenue": r.get("total_revenue_cny", 0),
                "churn": r.get("churn_rate", 0),
                "status": r.get("status", "dead"),
            })

    # Sort and tag
    competitors.sort(key=lambda c: c["score"], reverse=True)
    for c in competitors:
        if c["status"] == "dead":
            if c["purchasers"] == 0:
                c["death_cause"] = _t("evidence_tab.death_no_buyers")
            elif c["churn"] > 0.5:
                c["death_cause"] = _t("evidence_tab.death_high_churn")
            else:
                c["death_cause"] = _t("evidence_tab.death_low_score")
        else:
            c["death_cause"] = None

    return competitors


def generate_risk_signals(product_id: str, buyer_profile: dict, coupling_stats: dict) -> list[dict]:
    """Identify risk signals from simulation data."""
    risks = []
    segments = buyer_profile.get("segments", [])

    # Price sensitivity risk
    price_seg = next((s for s in segments if s["name"] == _t("evidence_tab.price_sensitive_seg")), None)
    if price_seg and price_seg["pct"] > 50:
        risks.append({"level": "medium", "signal": _t("evidence_tab.risk_price_sensitive"),
                       "detail": _t("evidence_tab.risk_price_detail", pct=price_seg["pct"])})

    # SMB sentiment risk
    smb_sentiment = coupling_stats.get("smb", {}).get("final_sentiment", 0) if isinstance(coupling_stats, dict) else 0
    if smb_sentiment < 0:
        risks.append({"level": "medium", "signal": _t("evidence_tab.risk_smb_sentiment"),
                       "detail": _t("evidence_tab.risk_smb_detail", s=smb_sentiment)})

    # Low buyer count risk
    if buyer_profile.get("total_buyers", 0) < 5:
        risks.append({"level": "high", "signal": _t("evidence_tab.risk_low_buyers"),
                       "detail": _t("evidence_tab.risk_low_detail", n=buyer_profile["total_buyers"])})

    # No risk = good
    if not risks:
        risks.append({"level": "low", "signal": _t("evidence_tab.risk_none"), "detail": _t("evidence_tab.risk_none_detail")})

    return risks


def generate_testable_hypotheses(product_id: str, reasons: list, buyer_profile: dict,
                                  product_info: dict) -> list[dict]:
    """Generate testable hypotheses from simulation evidence."""
    hypotheses = []

    # Price hypothesis
    pricing = product_info.get("estimated_pricing_cny", "")
    if pricing and buyer_profile.get("total_buyers", 0) > 0:
        hypotheses.append({
            "id": "H1",
            "hypothesis": _t("evidence_tab.hypothesis_price", p=pricing),
            "test": _t("evidence_tab.hypothesis_price_test", p=pricing),
            "source": _t("evidence_tab.hypothesis_price_source", n=buyer_profile["total_buyers"]),
        })

    # Motivation hypothesis
    if reasons:
        # Find most common fear-related reason
        fear_reasons = [r for r in reasons if any(w in r.get("reasoning", "").lower()
                        for w in ["fear", "怕", "担心", "焦虑", "泄露", "安全"])]
        if fear_reasons:
            hypotheses.append({
                "id": "H2",
                "hypothesis": _t("evidence_tab.hypothesis_fear"),
                "test": _t("evidence_tab.hypothesis_fear_test"),
                "source": _t("evidence_tab.hypothesis_fear_source", n=len(fear_reasons)),
            })

    # Social proof hypothesis
    hypotheses.append({
        "id": "H3",
        "hypothesis": _t("evidence_tab.hypothesis_social"),
        "test": _t("evidence_tab.hypothesis_social_test"),
        "source": _t("evidence_tab.hypothesis_social_source"),
    })

    return hypotheses


def generate_evidence_report(product_info: dict, agent_states: dict, agents: list,
                              all_results: list, coupling_history: list = None,
                              coupling_stats: dict = None) -> dict:
    """
    Generate a complete evidence report for one product.

    Args:
        product_info: Product dict with id, name, survival_score, etc.
        agent_states: Full agent_states dict from simulation
        agents: Agent profile list
        all_results: All simulation results for comparison
        coupling_history: Coupling events per round (optional)
        coupling_stats: Per-market coupling summary (optional)

    Returns:
        Structured evidence report dict
    """
    pid = product_info.get("product_id", product_info.get("id", ""))
    name = product_info.get("product_name", product_info.get("name", "Unknown"))

    # 1. Purchase reasons
    reasons = extract_purchase_reasons(pid, agent_states)

    # 2. Buyer profile
    buyer_profile = build_buyer_profile(pid, agent_states, agents)

    # 3. FOMO events
    fomo_events = detect_fomo_events(pid, coupling_history or [])

    # 4. Competitor comparison
    competitors = compare_with_competitors(pid, all_results)

    # 5. Risk signals
    risks = generate_risk_signals(pid, buyer_profile, coupling_stats or {})

    # 6. Testable hypotheses
    hypotheses = generate_testable_hypotheses(pid, reasons, buyer_profile, product_info)

    # Aggregate top reasons
    reason_counter = Counter()
    for r in reasons:
        text = r.get("reasoning", "")
        # Simple keyword-based categorization
        for keyword, label in [
            ("怕", _t("evidence_tab.motivation_fear")), ("担心", _t("evidence_tab.motivation_fear")), ("安全", _t("evidence_tab.motivation_safety")),
            ("简单", _t("evidence_tab.motivation_simple")), ("一键", _t("evidence_tab.motivation_simple")), ("方便", _t("evidence_tab.motivation_convenient")),
            ("便宜", _t("evidence_tab.motivation_price")), ("不贵", _t("evidence_tab.motivation_price")), ("值得", _t("evidence_tab.motivation_value")),
            ("朋友", _t("evidence_tab.motivation_social")), ("推荐", _t("evidence_tab.motivation_social")), ("试试", _t("evidence_tab.motivation_curious")),
        ]:
            if keyword in text:
                reason_counter[label] += 1
                break
        else:
            reason_counter[_t("evidence_tab.motivation_other")] += 1

    top_reasons = [{"category": cat, "count": cnt} for cat, cnt in reason_counter.most_common(5)]

    # Sample buyer quotes (up to 3)
    quotes = []
    for r in reasons[:10]:
        profile = agent_states.get(r["agent_id"], {}).get("profile", {})
        budget = profile.get("budget_monthly_cny", "?")
        dtype = profile.get("decision_speed", "?")
        quotes.append({
            "agent_id": r["agent_id"],
            "budget": budget,
            "type": dtype,
            "quote": r["reasoning"],
        })

    return {
        "product_id": pid,
        "product_name": name,
        "survival_score": product_info.get("survival_score", 0),
        "status": product_info.get("status", "unknown"),
        "purchasers": product_info.get("purchasers", 0),
        "revenue": product_info.get("total_revenue_cny", 0),
        "churn_rate": product_info.get("churn_rate", 0),

        "purchase_motivation": {
            "total_reasons_collected": len(reasons),
            "top_categories": top_reasons,
        },
        "buyer_profile": buyer_profile,
        "sample_quotes": quotes[:3],
        "fomo_events": fomo_events,
        "competitor_analysis": competitors,
        "risk_signals": risks,
        "testable_hypotheses": hypotheses,
    }


def generate_all_reports(pipeline_result: dict, agent_states: dict = None,
                          agents: list = None) -> list[dict]:
    """Generate evidence reports for all products in a pipeline result."""
    sim_results = pipeline_result.get("final_report", {}).get("simulation_results", [])
    if not sim_results:
        # Try direct from stages
        sim_results = []
        for r in pipeline_result.get("stages", {}).get("simulation", {}).get("results", []):
            sim_results.append(r)

    # Build agent_states from the pipeline log if not provided
    if agent_states is None:
        agent_states = _rebuild_agent_states_from_log(pipeline_result)

    if agents is None:
        agents = pipeline_result.get("stages", {}).get("agents_v2", {}).get("agents", [])

    coupling_stats = pipeline_result.get("stages", {}).get("simulation", {}).get("cross_domain_coupling", {})

    reports = []
    seen = set()
    for p in sim_results:
        pid = p.get("product_id", p.get("id", ""))
        if pid in seen:
            continue
        seen.add(pid)
        report = generate_evidence_report(
            p, agent_states, agents, sim_results,
            coupling_stats=coupling_stats,
        )
        reports.append(report)

    return reports


def _rebuild_agent_states_from_log(pipeline_result: dict) -> dict:
    """Rebuild agent_states from the simulation log (for post-hoc evidence extraction)."""
    states = {}

    # ── Build agent profile lookup ──
    agent_profiles = {}
    agents_data = pipeline_result.get("stages", {}).get("agents_v2", {})
    if isinstance(agents_data, dict) and "agents" in agents_data:
        for a in agents_data["agents"]:
            agent_profiles[a["id"]] = a

    # ── Build RL strategy lookup from pipeline RL summary ──
    # RL summary is stored in simulation stage under economic_alignment_rl
    # The raw strategies per agent are in the simulate() return but not saved.
    # We reconstruct basic strategy from agent profile defaults.
    # Future: save per-agent strategies in pipeline output.

    # ── Rebuild from sim_log ──
    sim_stage = pipeline_result.get("stages", {}).get("simulation", {})
    log = sim_stage.get("sim_log", sim_stage.get("log", []))

    for entry in log:
        if not isinstance(entry, dict):
            continue
        aid = entry.get("agent_id", "")
        if not aid:
            continue

        if aid not in states:
            profile = agent_profiles.get(aid, {})
            states[aid] = {
                "profile": profile,
                "history": [],
                "purchased_products": {},
                "discovered_products": set(),
                "total_spent": 0,
                "emotional_state": "neutral",
                "rl_strategy": {},
            }

        state = states[aid]
        pid = entry.get("product_id")
        action = entry.get("action", "ignore")
        rnd = entry.get("round", 0)

        # Track history
        state["history"].append(entry)
        state["emotional_state"] = entry.get("emotional_state", "neutral")

        # Rebuild purchased_products from purchase/churn actions
        if action == "purchase" and pid:
            wtp = _safe_float(entry.get("willingness_to_pay_cny", 0))
            state["purchased_products"][pid] = {"round": rnd, "price_paid": wtp}
            state["total_spent"] += wtp
            state["discovered_products"].add(pid)
        elif action == "discover" and pid:
            state["discovered_products"].add(pid)
        elif action == "churn" and pid and pid in state["purchased_products"]:
            state["purchased_products"][pid]["churned_at"] = rnd

    return states


def _safe_float(v, default=0.0):
    """Handle string/none values from LLM output."""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default
