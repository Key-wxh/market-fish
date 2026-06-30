"""
5-Stage Full Pipeline Orchestrator.
Runs the complete MarketFish pipeline: Ontology → Graph → Agents+Idea → Simulation → Report.
"""

import json
import time
from engine.ontology_generator import generate_ontology
from engine.graph_builder import build_knowledge_graph
from engine.agent_factory import generate_agents
from engine.idea_generator import generate_product_directions
from engine.simulator import simulate
from engine.reporter import generate_report


class Pipeline:
    def __init__(self):
        self.status = "idle"
        self.stages_completed = []
        self.errors = []

    def run(self, seed_data: dict) -> dict:
        """Run the full 5-stage pipeline."""
        start_time = time.time()
        output = {"pipeline_version": "1.0", "stages": {}}

        try:
            # Stage 1: Ontology
            self.status = "stage1_ontology"
            print("  [STAGE 1/5] Ontology...", flush=True)
            ontology = generate_ontology(seed_data)
            output["stages"]["ontology"] = {"status": "ok", "participant_types": len(ontology.get("participant_types", []))}
            self.stages_completed.append("ontology")
            print(f"  [STAGE 1/5] Ontology OK — {len(ontology.get('participant_types', []))} types", flush=True)

            # Stage 2: Knowledge Graph
            self.status = "stage2_graph"
            print("  [STAGE 2/5] Knowledge Graph...", flush=True)
            knowledge_graph = build_knowledge_graph(ontology, seed_data)
            output["stages"]["graph"] = {"status": "ok", "entities": len(knowledge_graph.get("entities", [])), "pain_spaces": len(knowledge_graph.get("pain_point_spaces", []))}
            self.stages_completed.append("graph")
            print(f"  [STAGE 2/5] Graph OK — {len(knowledge_graph.get('entities', []))} entities, {len(knowledge_graph.get('pain_point_spaces', []))} pain spaces", flush=True)

            # Stage 3a: Agent Generation
            self.status = "stage3a_agents"
            print("  [STAGE 3/5] Agent Generation...", flush=True)
            # Placeholder product directions for agent generation context
            placeholder_dirs = [{"id": "placeholder", "name": "Placeholder — real directions generated in 3b"}]
            agents_data = generate_agents(knowledge_graph, placeholder_dirs)
            output["stages"]["agents"] = {"status": "ok", "count": len(agents_data.get("agents", []))}
            self.stages_completed.append("agents")

            # Stage 3b: Product Direction Generation
            self.status = "stage3b_ideas"
            print("  [STAGE 3/5] Product Ideas...", flush=True)
            product_directions = generate_product_directions(knowledge_graph)
            output["stages"]["ideas"] = {"status": "ok", "count": len(product_directions)}
            print(f"  [STAGE 3/5] Ideas OK — {len(product_directions)} directions", flush=True)

            # Backtest filter — score directions against validated success factors
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

            # Stage 4: Market Simulation (run for each market type)
            self.status = "stage4_simulation"
            print("  [STAGE 4/5] Market Simulation (30 rounds, coupling + RL)...", flush=True)
            all_results = []
            coupling_stats = {}
            rl_stats = {}
            market_types = [
                ("b2c", [a for a in agents if a.get("type") == "consumer"]),
                ("smb", [a for a in agents if a.get("type") == "smb"]),
            ]

            # Filter product directions per market type
            for market_type, market_agents in market_types:
                if not market_agents:
                    continue
                relevant_products = [
                    p for p in product_directions
                    if p.get("target_market") == market_type or p.get("target_market") == "consumer"
                ]
                if not relevant_products:
                    relevant_products = product_directions[:3]

                sim_result = simulate(
                    agents=market_agents + [a for a in agents if a.get("type") in ("competitor", "environment")],
                    product_directions=relevant_products,
                    rounds=30,
                    market_type=market_type,
                )
                all_results.extend(sim_result.get("results", []))

                # Capture coupling & RL stats from each market simulation
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

        return output
