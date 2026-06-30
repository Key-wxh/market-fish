"""
5-Stage Full Pipeline Orchestrator.
Supports three input modes: explore / validate / hybrid.
"""

import json
import time
from engine.config import pipeline_cfg as _cfg
from engine.ontology_generator import generate_ontology
from engine.graph_builder import build_knowledge_graph
from engine.agent_factory import generate_agents
from engine.idea_generator import generate_product_directions
from engine.simulator import simulate
from engine.reporter import generate_report


def _convert_user_product(user_product: dict) -> dict:
    """Convert user-provided product description to product_directions format."""
    target = user_product.get("target_market", "consumer")
    # Infer category from target_market
    category_map = {"consumer": "consumer_app", "smb": "B2B_saas", "enterprise": "B2B_saas"}
    category = user_product.get("category", category_map.get(target, "consumer_app"))

    return {
        "id": user_product.get("id", f"user-prod-{hash(user_product.get('name', '')) % 10000:04d}"),
        "name": user_product.get("name", "Untitled Product"),
        "category": category,
        "target_market": target,
        "pain_point_addressed": user_product.get("pain_point", user_product.get("description", "")),
        "why_graph_shows_opportunity": user_product.get("differentiation", "User-submitted product for validation"),
        "estimated_pricing_cny": user_product.get("pricing", ""),
        "technical_feasibility": 0.8,
        "viral_potential": 0.5,
        "key_risks": user_product.get("key_risks", []),
        "similar_existing": "",
        "_source": "user",  # Tag to distinguish from LLM-generated
    }


def _load_seed_data(seed_data: dict = None) -> dict:
    """Load seed data from user-provided dict or default JSON files."""
    if seed_data:
        return seed_data

    seed = {}
    seed_files = {
        "freelancer": "data/seed_freelancer.json",
        "economy": "data/seed_economy.json",
        "tech": "data/seed_tech.json",
        "consumer": "data/seed_consumer.json",
        "b2b": "data/seed_b2b.json",
    }
    for key, path in seed_files.items():
        try:
            with open(path, encoding="utf-8") as f:
                seed[key] = json.load(f)
        except FileNotFoundError:
            print(f"  [WARN] Seed data missing: {path}", flush=True)
    return seed


class Pipeline:
    def __init__(self):
        self.status = "idle"
        self.stages_completed = []
        self.errors = []

    def run(self, seed_data: dict = None, mode: str = "explore",
            user_product: dict = None) -> dict:
        """
        Run the MarketFish pipeline.

        Args:
            seed_data: Market seed data dict. If None, loads from default JSON files.
            mode: "explore" (LLM generates directions),
                  "validate" (user injects product, skips idea_generator),
                  "hybrid" (user product + LLM-generated competitors)
            user_product: Product dict for validate/hybrid modes.
                Schema: {name, description, target_market, pricing, [pain_point, differentiation]}

        Returns:
            Pipeline result dict with stages, product_directions, and final_report.
        """
        start_time = time.time()
        mode_label = {"explore": "A: 探索", "validate": "B: 验证", "hybrid": "C: 混合"}.get(mode, mode)
        output = {"pipeline_version": "2.0", "input_mode": mode, "stages": {}}

        # Load seed data
        seed = _load_seed_data(seed_data)

        try:
            # Stage 1: Ontology
            self.status = "stage1_ontology"
            print(f"  [STAGE 1/5] Ontology ({mode_label})...", flush=True)
            ontology = generate_ontology(seed)
            output["stages"]["ontology"] = {"status": "ok", "participant_types": len(ontology.get("participant_types", []))}
            self.stages_completed.append("ontology")
            print(f"  [STAGE 1/5] Ontology OK — {len(ontology.get('participant_types', []))} types", flush=True)

            # Stage 2: Knowledge Graph
            self.status = "stage2_graph"
            print("  [STAGE 2/5] Knowledge Graph...", flush=True)
            knowledge_graph = build_knowledge_graph(ontology, seed)
            output["stages"]["graph"] = {"status": "ok", "entities": len(knowledge_graph.get("entities", [])), "pain_spaces": len(knowledge_graph.get("pain_point_spaces", []))}
            self.stages_completed.append("graph")
            print(f"  [STAGE 2/5] Graph OK — {len(knowledge_graph.get('entities', []))} entities, {len(knowledge_graph.get('pain_point_spaces', []))} pain spaces", flush=True)

            # Stage 3a: Agent Generation (first pass with placeholder)
            self.status = "stage3a_agents"
            print("  [STAGE 3/5] Agent Generation...", flush=True)
            placeholder_dirs = [{"id": "placeholder", "name": "Placeholder — real directions generated in 3b"}]
            agents_data = generate_agents(knowledge_graph, placeholder_dirs)
            output["stages"]["agents"] = {"status": "ok", "count": len(agents_data.get("agents", []))}
            self.stages_completed.append("agents")

            # ── Stage 3b: Product Directions (mode-dependent) ──
            self.status = "stage3b_ideas"
            product_directions = []

            if mode == "validate":
                # User's product only, skip LLM generation
                print("  [STAGE 3/5] Product: user-injected (validate mode)...", flush=True)
                if not user_product:
                    raise ValueError("validate mode requires user_product")
                converted = _convert_user_product(user_product)
                product_directions = [converted]
                output["stages"]["ideas"] = {"status": "ok", "count": 1, "source": "user"}
                print(f"  [STAGE 3/5] Injected: {converted['name']}", flush=True)

            elif mode == "hybrid":
                # User's product + LLM-generated
                print("  [STAGE 3/5] Product: user + AI (hybrid mode)...", flush=True)
                if not user_product:
                    raise ValueError("hybrid mode requires user_product")
                llm_dirs = generate_product_directions(knowledge_graph)
                converted = _convert_user_product(user_product)
                product_directions = [converted] + llm_dirs
                output["stages"]["ideas"] = {"status": "ok", "count": len(product_directions), "source": "hybrid", "user_product": 1, "llm_generated": len(llm_dirs)}
                print(f"  [STAGE 3/5] User: {converted['name']} + {len(llm_dirs)} AI-generated", flush=True)

            else:  # explore (default)
                print("  [STAGE 3/5] Product Ideas (explore mode)...", flush=True)
                product_directions = generate_product_directions(knowledge_graph)
                output["stages"]["ideas"] = {"status": "ok", "count": len(product_directions), "source": "llm"}
                print(f"  [STAGE 3/5] Ideas OK — {len(product_directions)} directions", flush=True)

            # Backtest filter
            from engine.backtest_filter import filter_and_rank
            product_directions = filter_and_rank(product_directions)
            promising = sum(1 for d in product_directions if d.get("backtest_verdict") == "promising")
            print(f"  [FILTER] {len(product_directions)} directions: {promising} promising, {len(product_directions)-promising} risky/fail", flush=True)
            output["stages"]["backtest_filter"] = {"status": "ok", "promising": promising, "total": len(product_directions)}
            output["product_directions"] = product_directions
            self.stages_completed.append("ideas")

            # Stage 3b-bis: Re-generate agents with real product directions
            self.status = "stage3b_agents_v2"
            agents_data = generate_agents(knowledge_graph, product_directions)
            agents = agents_data.get("agents", [])
            output["stages"]["agents_v2"] = {"status": "ok", "count": len(agents)}

            # Stage 4: Market Simulation
            self.status = "stage4_simulation"
            print("  [STAGE 4/5] Market Simulation (30 rounds, coupling + RL)...", flush=True)
            all_results = []
            coupling_stats = {}
            rl_stats = {}

            _market_config = _cfg()["market_types"]
            market_types = []
            for m in _market_config:
                if m == "b2c":
                    market_types.append((m, [a for a in agents if a.get("type") == "consumer"]))
                elif m == "smb":
                    market_types.append((m, [a for a in agents if a.get("type") == "smb"]))
                else:
                    market_types.append((m, [a for a in agents if a.get("type") == m]))

            for market_type, market_agents in market_types:
                if not market_agents:
                    continue
                relevant_products = [
                    p for p in product_directions
                    if p.get("target_market") == market_type or p.get("target_market") == _cfg()["target_market_fallback"]
                ]
                if not relevant_products:
                    relevant_products = product_directions[:_cfg()["product_fallback_count"]]

                sim_result = simulate(
                    agents=market_agents + [a for a in agents if a.get("type") in ("competitor", "environment")],
                    product_directions=relevant_products,
                    rounds=_cfg()["simulation_rounds"],
                    market_type=market_type,
                )
                all_results.extend(sim_result.get("results", []))

                # Save simulation log for post-hoc evidence extraction
                output["stages"]["simulation"]["sim_log"].extend(sim_result.get("log", []))

                if sim_result.get("coupling_history"):
                    coupling_stats[market_type] = {
                        "rounds": len(sim_result["coupling_history"]),
                        "final_sentiment": sim_result["coupling_history"][-1]["market_signals"]["avg_sentiment"] if sim_result["coupling_history"] else 0,
                    }
                if sim_result.get("rl_summary"):
                    rl_stats[market_type] = sim_result["rl_summary"]

            output["stages"]["simulation"] = {
                "status": "ok",
                "markets_simulated": len(market_types),
                "total_results": len(all_results),
                "cross_domain_coupling": coupling_stats,
                "economic_alignment_rl": rl_stats,
                "sim_log": [],  # populated per-market below
            }
            self.stages_completed.append("simulation")

            # Stage 5: Report Generation
            self.status = "stage5_report"
            print("  [STAGE 5/5] Report Generation...", flush=True)
            report = generate_report(all_results, knowledge_graph)
            output["stages"]["report"] = {"status": "ok", "perspectives": len(report.get("analyst_reports", []))}
            output["final_report"] = report
            self.stages_completed.append("report")

            self.status = "complete"
            output["pipeline_status"] = "complete"
            output["elapsed_seconds"] = round(time.time() - start_time, 1)
            output["stages_completed"] = self.stages_completed

        except Exception as e:
            self.status = f"error_at_{self.status}"
            self.errors.append(str(e))
            output["pipeline_status"] = "error"
            output["error"] = str(e)
            output["failed_at_stage"] = self.status
            output["stages_completed"] = self.stages_completed
            import traceback
            output["traceback"] = traceback.format_exc()
            print(f"  [ERROR] {e}", flush=True)
            traceback.print_exc()

        return output
