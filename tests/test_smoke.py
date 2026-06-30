"""
Smoke test suite — no LLM calls. Verifies all modules load and basic functions work.
Run: python -m pytest tests/test_smoke.py -v
"""

import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfig:
    """Verify config loading and parameter access."""

    def test_config_loads(self):
        from engine.config import get_config
        cfg = get_config()
        assert len(cfg) >= 10, f"Expected >=10 sections, got {len(cfg)}"
        assert "pipeline" in cfg
        assert "simulation" in cfg
        assert "coupling" in cfg
        assert "rl" in cfg

    def test_pipeline_params(self):
        from engine.config import pipeline_cfg
        p = pipeline_cfg()
        assert p["simulation_rounds"] == 30
        assert "b2c" in p["market_types"]

    def test_calibration_cases(self):
        from engine.config import calibration_cases
        cases = calibration_cases()
        assert len(cases) == 6
        outcomes = [c["outcome"] for c in cases]
        assert "success" in outcomes
        assert "failure" in outcomes
        assert "untested" in outcomes

    def test_agent_batches(self):
        from engine.config import agent_batches
        batches = agent_batches()
        assert len(batches) == 8
        total = sum(b["count"] for b in batches)
        assert total == 128


class TestModelRegistry:
    """Verify model registry loading."""

    def test_registry_loads(self):
        from engine.model_registry import ModelRegistry
        r = ModelRegistry()
        providers = r.list_providers()
        assert len(providers) >= 6
        assert "deepseek" in providers
        assert "openai" in providers

    def test_list_active_models(self):
        from engine.model_registry import ModelRegistry
        r = ModelRegistry()
        models = r.list_active_models("deepseek")
        assert len(models) >= 1

    def test_status_report(self):
        from engine.model_registry import ModelRegistry
        r = ModelRegistry()
        status = r.status_report()
        assert "deepseek" in status
        assert "key_configured" in status["deepseek"]


class TestCoupling:
    """Verify coupling engine functions."""

    def test_emotion_valence(self):
        from engine.coupling import _emotion_valence
        assert _emotion_valence("excited") > 0
        assert _emotion_valence("frustrated") < 0
        assert _emotion_valence("neutral") == 0.0

    def test_adjust_wtp(self):
        from engine.coupling import adjust_willingness_to_pay
        assert adjust_willingness_to_pay("excited", 100) > 100
        assert adjust_willingness_to_pay("frustrated", 100) < 100

    def test_apply_coupling(self):
        from engine.coupling import apply_coupling
        agents = [{"id": f"a{i}", "type": "consumer", "name": f"C{i}",
                    "social_network": {"connections": [], "network_type": "small_world"},
                    "influence_weight": 1.0} for i in range(10)]
        states = {}
        for a in agents:
            states[a["id"]] = {
                "profile": a, "history": [], "discovered_products": set(),
                "purchased_products": {}, "total_spent": 0, "emotional_state": "neutral",
            }
        stats = apply_coupling(states, 1, [])
        assert "market_signals" in stats
        assert "adoption_rate" in stats["market_signals"]


class TestRL:
    """Verify RL strategy functions."""

    def test_init_strategy(self):
        from engine.alignment_rl import init_strategy
        profile = {"type": "consumer", "tech_savviness": 0.5, "budget_monthly_cny": 500,
                    "decision_speed": "days", "influence_weight": 1.0, "bdi": {"desires": ["save time"]}}
        s = init_strategy(profile)
        for key in ["price_sensitivity", "early_adopter", "social_susceptibility", "loyalty", "risk_tolerance"]:
            assert key in s
            assert 0 <= s[key] <= 1

    def test_update_strategies(self):
        from engine.alignment_rl import init_strategy, update_all_strategies
        states = {}
        for i in range(10):
            aid = f"a{i}"
            profile = {"type": "consumer", "tech_savviness": 0.5, "budget_monthly_cny": 500,
                        "decision_speed": "days", "influence_weight": 1.0, "bdi": {"desires": ["save time"]}}
            states[aid] = {
                "profile": profile, "history": [], "purchased_products": {},
                "rl_strategy": init_strategy(profile),
            }
        market = {"avg_sentiment": 0.2, "adoption_rate": 0.3, "trending_products": []}
        result = update_all_strategies(states, market, [])
        assert result["agents_updated"] == 10


class TestNetwork:
    """Verify small-world network functions."""

    def test_build_network(self):
        from engine.network import build_agent_network, network_stats
        agents = [{"id": f"a{i}"} for i in range(20)]
        agents = build_agent_network(agents)
        stats = network_stats(agents)
        assert stats["agents"] == 20
        assert stats["total_edges"] > 0
        assert stats["avg_degree"] >= 2

    def test_watts_strogatz(self):
        from engine.network import watts_strogatz_network
        network = watts_strogatz_network(20, 4, 0.1)
        assert len(network) == 20
        for node in network:
            assert len(node["connections"]) >= 2


class TestSimulator:
    """Verify simulator helper functions."""

    def test_safe_float(self):
        from engine.simulator import _safe_float
        assert _safe_float("5.0") == 5.0
        assert _safe_float(None) == 0.0
        assert _safe_float("abc") == 0.0
        assert _safe_float(10) == 10.0

    def test_compute_results(self):
        from engine.simulator import _compute_results
        states = {}
        for i in range(30):
            aid = f"a{i}"
            purchased = {"p1": {"round": 5, "price_paid": 20}} if i < 10 else {}
            states[aid] = {"purchased_products": purchased}
        products = [{"id": "p1", "name": "Test"}]
        results = _compute_results(states, products)
        assert len(results) == 1
        assert results[0]["survival_score"] > 0
        assert results[0]["status"] in ("alive", "struggling", "dead")


class TestBacktestFilter:
    """Verify backtest filter scoring."""

    def test_score_direction_consumer(self):
        from engine.backtest_filter import score_direction
        d = {"name": "One-Click Scanner", "description": "one-click instant scan, no login",
             "category": "consumer_app", "target_market": "consumer", "estimated_pricing_cny": "¥5"}
        r = score_direction(d)
        assert r["backtest_score"] >= 50  # simple_ux + consumer
        assert r["backtest_verdict"] == "promising"

    def test_score_direction_b2b(self):
        from engine.backtest_filter import score_direction
        d = {"name": "B2B Dashboard", "description": "enterprise analytics platform",
             "category": "B2B_saas", "target_market": "smb", "estimated_pricing_cny": "¥299/month"}
        r = score_direction(d)
        assert r["backtest_score"] < 30  # Should be risky or fail


class TestPipeline:
    """Verify pipeline structure and mode support."""

    def test_pipeline_init(self):
        from engine.pipeline import Pipeline
        p = Pipeline()
        assert p.status == "idle"

    def test_convert_user_product(self):
        from engine.pipeline import _convert_user_product
        up = {"name": "Test", "description": "Test desc", "target_market": "consumer", "pricing": "¥5"}
        d = _convert_user_product(up)
        assert d["name"] == "Test"
        assert d["_source"] == "user"
        assert d["target_market"] == "consumer"
        assert d["category"] == "consumer_app"

    def test_run_accepts_modes(self):
        import inspect
        from engine.pipeline import Pipeline
        sig = inspect.signature(Pipeline.run)
        params = list(sig.parameters.keys())
        assert "mode" in params
        assert "user_product" in params


class TestCalibrate:
    """Verify calibration module."""

    def test_build_product(self):
        from engine.calibrate import build_calibration_product
        from engine.config import calibration_cases
        case = calibration_cases()[0]
        p = build_calibration_product(case)
        assert p["_calibration_outcome"] == case["outcome"]
        assert "id" in p

    def test_build_agents(self):
        from engine.calibrate import build_calibration_agents
        agents = build_calibration_agents()
        assert len(agents) >= 20
        types = set(a["type"] for a in agents)
        assert "consumer" in types
        assert "smb" in types

    def test_analyze_patterns(self):
        from engine.calibrate import analyze_patterns
        r = analyze_patterns()
        assert r["success_count"] >= 2
        assert r["failure_count"] >= 1

    def test_baseline_keyword(self):
        from engine.calibrate import baseline_keyword
        from engine.config import calibration_cases
        r = baseline_keyword(calibration_cases()[0])
        assert r["method"] == "keyword_filter"
        assert r["predicted"] in ("success", "failure")

    def test_baseline_random(self):
        from engine.calibrate import baseline_random
        r = baseline_random()
        assert r["predicted"] in ("success", "failure")


if __name__ == "__main__":
    # Run all tests without pytest
    import traceback
    tests = [
        TestConfig(), TestModelRegistry(), TestCoupling(), TestRL(),
        TestNetwork(), TestSimulator(), TestBacktestFilter(),
        TestPipeline(), TestCalibrate(),
    ]
    passed = failed = 0
    for test_cls in tests:
        name = test_cls.__class__.__name__
        for method_name in dir(test_cls):
            if method_name.startswith("test_"):
                try:
                    getattr(test_cls, method_name)()
                    print(f"  PASS {name}.{method_name}")
                    passed += 1
                except Exception as e:
                    print(f"  FAIL {name}.{method_name}: {e}")
                    failed += 1

    print(f"\n=== {passed} passed, {failed} failed ===")
    if failed:
        sys.exit(1)
