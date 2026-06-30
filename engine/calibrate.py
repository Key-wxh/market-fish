"""
Calibration Module — simulation-based validation against known products.
Replaces keyword-matching backtest with actual market simulation.

Merges engine/backtest.py (was orphaned).
Follows directional validation framework (not statistical significance — only 6 cases).
"""

import json, time, random
from engine.config import calibration_cases, simulation_cfg, backtest_cfg


# ── Calibration product conversion ──

def build_calibration_product(case: dict) -> dict:
    """Convert a CALIBRATION_CASE to product_directions format."""
    target = case.get("target_market", "consumer")
    category_map = {"consumer": "consumer_app", "smb": "B2B_saas", "enterprise": "B2B_saas"}
    category = case.get("category", category_map.get(target, "consumer_app"))

    # Compute viral_potential from factors
    factors = case.get("factors", [])
    viral = 0.8 if "social_sharing" in factors else 0.3

    return {
        "id": f"calib-{case['id']}",
        "name": case["name"],
        "category": category,
        "target_market": target,
        "pain_point_addressed": case.get("description", ""),
        "why_graph_shows_opportunity": f"Known outcome: {case.get('outcome', '?')}. {case.get('evidence', '')}",
        "estimated_pricing_cny": case.get("pricing", ""),
        "technical_feasibility": 0.9,
        "viral_potential": viral,
        "key_risks": [],
        "similar_existing": "",
        "_calibration_outcome": case.get("outcome"),  # Ground truth
        "_calibration_evidence": case.get("evidence", ""),
    }


# ── Fast calibration agents (no LLM generation needed) ──

def build_calibration_agents() -> list:
    """Build a small but diverse agent set for fast calibration (~25 agents, no LLM needed)."""
    agents = []
    agent_id = 0

    # 12 consumers with varied profiles
    consumer_profiles = [
        ("impulse", 200, 0.4, 2.0), ("impulse", 500, 0.6, 1.5), ("impulse", 800, 0.5, 1.0),
        ("days", 300, 0.3, 1.0), ("days", 600, 0.5, 1.5), ("days", 1000, 0.7, 2.0),
        ("weeks", 150, 0.2, 0.5), ("weeks", 400, 0.4, 1.0), ("weeks", 1500, 0.6, 1.5),
        ("impulse", 100, 0.3, 3.0), ("days", 2000, 0.8, 2.5), ("weeks", 250, 0.2, 0.5),
    ]
    for speed, budget, tech, influence in consumer_profiles:
        agents.append({
            "id": f"calib-consumer-{agent_id}", "type": "consumer",
            "name": f"Calib Consumer {agent_id}",
            "demographics": {"age": "25-40", "income_cny": f"{budget*2}-{budget*5}", "city_tier": str(random.randint(1,4))},
            "bdi": {"beliefs": ["AI tools are useful"], "desires": ["save time"], "intentions": ["try new apps"]},
            "budget_monthly_cny": budget, "pain_points": ["too many choices", "hard to find good tools"],
            "tech_savviness": tech, "decision_speed": speed, "influence_weight": influence,
            "social_network": {"connections": [], "network_type": "small_world"},
        })
        agent_id += 1

    # 6 SMBs
    for i in range(6):
        agents.append({
            "id": f"calib-smb-{agent_id}", "type": "smb",
            "name": f"Calib SMB {agent_id}",
            "demographics": {"age": "30-50", "income_cny": "10000-50000", "city_tier": str(random.randint(1,3))},
            "bdi": {"beliefs": ["efficiency matters"], "desires": ["reduce cost"], "intentions": ["evaluate tools"]},
            "budget_monthly_cny": 2000 + i * 1000,
            "pain_points": ["high labor cost", "customer acquisition"],
            "tech_savviness": 0.3 + i * 0.08, "decision_speed": "weeks", "influence_weight": 1.0 + i * 0.3,
            "social_network": {"connections": [], "network_type": "small_world"},
        })
        agent_id += 1

    # 3 competitors
    for i in range(3):
        agents.append({
            "id": f"calib-competitor-{agent_id}", "type": "competitor",
            "name": f"Calib Competitor {agent_id}",
            "demographics": {}, "bdi": {"beliefs": [], "desires": [], "intentions": []},
            "budget_monthly_cny": 5000, "pain_points": [],
            "tech_savviness": 0.8, "decision_speed": "months", "influence_weight": 2.0,
            "social_network": {"connections": [], "network_type": "small_world"},
        })
        agent_id += 1

    # 2 environment
    for i in range(2):
        agents.append({
            "id": f"calib-env-{agent_id}", "type": "environment",
            "name": f"Calib Environment {agent_id}",
            "demographics": {}, "bdi": {"beliefs": [], "desires": [], "intentions": []},
            "budget_monthly_cny": 0, "pain_points": [],
            "tech_savviness": 0.5, "decision_speed": "months", "influence_weight": 1.0,
            "social_network": {"connections": [], "network_type": "small_world"},
        })
        agent_id += 1

    # Apply small-world network
    from engine.network import build_agent_network
    agents = build_agent_network(agents)
    return agents


# ── Baselines ──

def baseline_keyword(case: dict) -> dict:
    """Backtest filter baseline — keyword-based scoring."""
    from engine.backtest_filter import score_direction
    product = build_calibration_product(case)
    result = score_direction(product)
    verdict = result.get("backtest_verdict", "risky")
    return {
        "method": "keyword_filter",
        "predicted": "success" if verdict == "promising" else "failure",
        "score": result.get("backtest_score", 0),
        "flags": result.get("backtest_flags", []),
    }


def baseline_random() -> dict:
    """Random baseline — 50% coin flip."""
    return {
        "method": "random",
        "predicted": "success" if random.random() > 0.5 else "failure",
    }


def baseline_single_llm(case: dict) -> dict:
    """Single LLM direct judgment — no simulation."""
    from engine.llm_client import get_llm

    product = build_calibration_product(case)
    prompt = f"""You are a product market analyst. Given this product description, predict whether it will succeed or fail in the market.

PRODUCT: {product['name']}
DESCRIPTION: {product['pain_point_addressed']}
TARGET: {product['target_market']}
PRICING: {product['estimated_pricing_cny']}

Output JSON: {{"prediction": "success" or "failure", "confidence": 0.0-1.0, "reasoning": "one sentence"}}"""

    try:
        llm = get_llm()
        result = llm.chat_json(system="You are a market analyst. Be honest and concise.", user=prompt, agent_type="default")
        return {
            "method": "single_llm",
            "predicted": result.get("prediction", "failure"),
            "confidence": result.get("confidence", 0.5),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        return {"method": "single_llm", "predicted": "failure", "error": str(e)}


# ── Simulation-based calibration ──

def run_calibration_case(case: dict, agents: list = None, rounds: int = 20,
                         runs: int = 3) -> dict:
    """Run simulation for one calibration case. Returns survival outcome + metrics."""
    from engine.simulator import simulate

    if agents is None:
        agents = build_calibration_agents()

    product = build_calibration_product(case)
    expected = case.get("outcome", "unknown")

    scores = []
    statuses = []
    for run_idx in range(runs):
        try:
            result = simulate(
                agents=agents,
                product_directions=[product],
                rounds=rounds,
                market_type=case.get("target_market", "consumer"),
            )
            sim_results = result.get("results", [])
            if sim_results:
                scores.append(sim_results[0].get("survival_score", 0))
                statuses.append(sim_results[0].get("status", "dead"))
            else:
                scores.append(0)
                statuses.append("dead")
        except Exception as e:
            scores.append(0)
            statuses.append("error")

    # Use mode survival_status across runs
    from collections import Counter
    mode_status = Counter(statuses).most_common(1)[0][0] if statuses else "dead"
    avg_score = sum(scores) / len(scores) if scores else 0

    predicted = "success" if mode_status == "alive" else "failure"
    match = (predicted == expected)

    return {
        "case_id": case["id"],
        "name": case["name"],
        "expected": expected,
        "predicted": predicted,
        "match": match,
        "avg_survival_score": round(avg_score, 3),
        "mode_status": mode_status,
        "per_run_scores": scores,
        "per_run_statuses": statuses,
    }


def run_full_calibration(agents: list = None, rounds: int = 20,
                         runs_per_case: int = 3, include_baselines: bool = True) -> dict:
    """
    Run calibration on all known cases.
    Returns accuracy metrics and per-case results.
    """
    cases = calibration_cases()
    tested_cases = [c for c in cases if c.get("outcome") != "untested"]
    untested_cases = [c for c in cases if c.get("outcome") == "untested"]

    if agents is None:
        agents = build_calibration_agents()

    print(f"  [CALIBRATE] {len(tested_cases)} tested + {len(untested_cases)} untested cases")
    print(f"  [CALIBRATE] {len(agents)} agents, {rounds} rounds, {runs_per_case} runs/case")
    print(f"  [CALIBRATE] Estimating {len(tested_cases) * runs_per_case * 5} min total...", flush=True)

    # Simulation results
    sim_results = []
    for case in tested_cases:
        print(f"  [CALIBRATE] Case: {case['name']} (expected: {case['outcome']})...", flush=True)
        t0 = time.time()
        r = run_calibration_case(case, agents, rounds, runs_per_case)
        elapsed = time.time() - t0
        icon = "+" if r["match"] else "x"
        print(f"    [{icon}] predicted={r['predicted']}, score={r['avg_survival_score']:.3f}, status={r['mode_status']} ({elapsed:.0f}s)", flush=True)
        sim_results.append(r)

    # Untested cases — predict only
    predictions = []
    for case in untested_cases:
        print(f"  [CALIBRATE] Predict: {case['name']} (untested)...", flush=True)
        r = run_calibration_case(case, agents, rounds, runs_per_case)
        predictions.append(r)

    # Baselines
    baselines = {}
    if include_baselines:
        # Keyword baseline (fast)
        kw_results = []
        for case in tested_cases:
            kw = baseline_keyword(case)
            kw["case_id"] = case["id"]
            kw["expected"] = case["outcome"]
            kw["match"] = (kw["predicted"] == case["outcome"])
            kw_results.append(kw)
        baselines["keyword_filter"] = {
            "accuracy": round(sum(1 for r in kw_results if r["match"]) / max(len(kw_results), 1), 3),
            "results": kw_results,
        }

        # Random baseline (theoretical)
        baselines["random"] = {"accuracy": 0.50, "note": "theoretical 50% for binary classification"}

    # Compute simulation metrics
    correct = sum(1 for r in sim_results if r["match"])
    accuracy = round(correct / max(len(sim_results), 1), 3)

    # Precision/Recall/F1
    tp = sum(1 for r in sim_results if r["predicted"] == "success" and r["expected"] == "success")
    fp = sum(1 for r in sim_results if r["predicted"] == "success" and r["expected"] == "failure")
    fn = sum(1 for r in sim_results if r["predicted"] == "failure" and r["expected"] == "success")
    tn = sum(1 for r in sim_results if r["predicted"] == "failure" and r["expected"] == "failure")

    precision = round(tp / max(tp + fp, 1), 3)
    recall = round(tp / max(tp + fn, 1), 3)
    f1 = round(2 * precision * recall / max(precision + recall, 0.001), 3)

    return {
        "calibration_date": time.strftime("%Y-%m-%d %H:%M"),
        "cases_tested": len(tested_cases),
        "cases_untested": len(untested_cases),
        "runs_per_case": runs_per_case,
        "agents_used": len(agents),
        "rounds": rounds,

        "simulation_metrics": {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "correct": correct,
            "total": len(tested_cases),
            "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        },

        "per_case_results": sim_results,
        "predictions_untested": predictions,
        "baselines": baselines,

        # Directional validation note (not statistical significance)
        "_note": f"Directional validation only — {len(tested_cases)} cases is insufficient for statistical significance. Simulation accuracy > keyword_accuracy > 0.50 indicates model provides information gain.",
    }


# ── Pattern analysis (merged from backtest.py) ──

def analyze_patterns(cases: list = None) -> dict:
    """Analyze success/failure patterns from known cases (merged from backtest.py)."""
    if cases is None:
        cases = calibration_cases()

    successes = [c for c in cases if c.get("outcome") == "success"]
    failures = [c for c in cases if c.get("outcome") == "failure"]

    factors = ["dead_simple_ux", "solves_real_fear", "social_sharing", "consumer_b2c"]
    factor_analysis = {}
    for f in factors:
        s_rate = sum(1 for c in successes if f in c.get("factors", [])) / max(len(successes), 1)
        f_rate = sum(1 for c in failures if f in c.get("factors", [])) / max(len(failures), 1)
        factor_analysis[f] = {
            "success_rate": round(s_rate, 2),
            "failure_rate": round(f_rate, 2),
            "discrimination": round(s_rate - f_rate, 2),
        }

    return {
        "cases_analyzed": len(cases),
        "success_count": len(successes),
        "failure_count": len(failures),
        "factor_analysis": factor_analysis,
    }
