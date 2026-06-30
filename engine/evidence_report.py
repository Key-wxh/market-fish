"""
Evidence Report Generator — translates simulation data into readable product reports.
The value expression layer of MarketFish.

Data sources: agent reasoning, RL strategies, coupling history, purchase timeline.
"""

import json
from collections import Counter, defaultdict


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
            strategy = state.get("rl_strategy", {})
            profile = state.get("profile", {})
            buyers.append({
                "agent_id": aid,
                "type": profile.get("type", "consumer"),
                "budget": profile.get("budget_monthly_cny", 0),
                "decision_speed": profile.get("decision_speed", "days"),
                "strategy": strategy,
            })

    if not buyers:
        return {"total_buyers": 0, "segments": []}

    # Cluster into segments based on strategy dimensions
    price_sensitive = [b for b in buyers if b.get("strategy", {}).get("price_sensitivity", 0) > 0.6]
    impulsive = [b for b in buyers if b.get("decision_speed") == "impulse"]
    rational = [b for b in buyers if b.get("strategy", {}).get("social_susceptibility", 0) < 0.3]

    total = len(buyers)
    return {
        "total_buyers": total,
        "avg_budget": round(sum(b["budget"] for b in buyers) / total, 1) if total else 0,
        "segments": [
            {"name": "价格敏感型", "count": len(price_sensitive), "pct": round(len(price_sensitive) / total * 100, 1),
             "description": "对价格高度敏感，倾向于低价或高性价比产品"},
            {"name": "冲动消费型", "count": len(impulsive), "pct": round(len(impulsive) / total * 100, 1),
             "description": "决策快，容易受情绪和 FOMO 影响"},
            {"name": "理性独立型", "count": len(rational), "pct": round(len(rational) / total * 100, 1),
             "description": "不易受社交影响，独立做决策"},
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
                c["death_cause"] = "零买家 — 产品与市场需求不匹配"
            elif c["churn"] > 0.5:
                c["death_cause"] = "高流失 — 用户试用后放弃"
            else:
                c["death_cause"] = "存活分数过低"
        else:
            c["death_cause"] = None

    return competitors


def generate_risk_signals(product_id: str, buyer_profile: dict, coupling_stats: dict) -> list[dict]:
    """Identify risk signals from simulation data."""
    risks = []
    segments = buyer_profile.get("segments", [])

    # Price sensitivity risk
    price_seg = next((s for s in segments if s["name"] == "价格敏感型"), None)
    if price_seg and price_seg["pct"] > 50:
        risks.append({"level": "medium", "signal": "买家价格敏感度过高",
                       "detail": f"{price_seg['pct']}% 买家为价格敏感型，提价空间有限"})

    # SMB sentiment risk
    smb_sentiment = coupling_stats.get("smb", {}).get("final_sentiment", 0) if isinstance(coupling_stats, dict) else 0
    if smb_sentiment < 0:
        risks.append({"level": "medium", "signal": "SMB 市场情绪负值",
                       "detail": f"SMB 商家情绪 {smb_sentiment:.2f}，企业端扩展需谨慎"})

    # Low buyer count risk
    if buyer_profile.get("total_buyers", 0) < 5:
        risks.append({"level": "high", "signal": "买家基数过小",
                       "detail": f"仅 {buyer_profile['total_buyers']} 个买家，统计可信度低"})

    # No risk = good
    if not risks:
        risks.append({"level": "low", "signal": "无明显风险信号", "detail": "当前模拟中未发现显著风险"})

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
            "hypothesis": f"定价 {pricing} 在目标用户群中可接受",
            "test": f"A/B test: {pricing} vs 更低/更高价位，观察转化率差异",
            "source": f"{buyer_profile['total_buyers']} 个买家接受当前价格",
        })

    # Motivation hypothesis
    if reasons:
        # Find most common fear-related reason
        fear_reasons = [r for r in reasons if any(w in r.get("reasoning", "").lower()
                        for w in ["fear", "怕", "担心", "焦虑", "泄露", "安全"])]
        if fear_reasons:
            hypotheses.append({
                "id": "H2",
                "hypothesis": "恐惧/焦虑是核心购买动机",
                "test": "落地页 A/B test: 恐惧驱动文案 vs 功能驱动文案",
                "source": f"{len(fear_reasons)} 个买家提及恐惧/安全相关理由",
            })

    # Social proof hypothesis
    hypotheses.append({
        "id": "H3",
        "hypothesis": "社交证明可显著提升转化",
        "test": "展示「已有多少人购买」 → 观察对转化率的影响",
        "source": "基于模拟中 FOMO 效应的观察",
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
            ("怕", "恐惧驱动"), ("担心", "恐惧驱动"), ("安全", "安全需求"),
            ("简单", "极简体验"), ("一键", "极简体验"), ("方便", "便捷性"),
            ("便宜", "价格合理"), ("不贵", "价格合理"), ("值得", "价值认同"),
            ("朋友", "社交影响"), ("推荐", "社交影响"), ("试试", "尝鲜心理"),
        ]:
            if keyword in text:
                reason_counter[label] += 1
                break
        else:
            reason_counter["其他"] += 1

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
    sim_stage = pipeline_result.get("stages", {}).get("simulation", {})
    log = []
    # The simulation log is in the full result's timeline
    for market_log in [pipeline_result.get("stages", {}).get("simulation", {}).get("log", [])]:
        if isinstance(market_log, list):
            log.extend(market_log)

    for entry in log:
        if not isinstance(entry, dict):
            continue
        aid = entry.get("agent_id", "")
        if aid not in states:
            states[aid] = {"profile": {}, "history": [], "purchased_products": {}, "emotional_state": "neutral", "rl_strategy": {}}
        states[aid]["history"].append(entry)
        states[aid]["emotional_state"] = entry.get("emotional_state", "neutral")

    return states
