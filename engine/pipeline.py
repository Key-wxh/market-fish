"""
5-Stage Full Pipeline Orchestrator.
Supports three input modes: explore / validate / hybrid.
"""

import json
import time
import random
import hashlib
from engine.config import pipeline_cfg as _cfg, pipeline_cfg as _pcfg, simulation_cfg as _sim_cfg
from engine.i18n import t as _t
from engine.ontology_generator import generate_ontology
from engine.graph_builder import build_knowledge_graph
from engine.agent_factory import generate_agents
from engine.idea_generator import generate_product_directions
from engine.simulator import simulate
from engine.reporter import generate_report


def _extract_sim_agent(record: dict) -> dict:
    """Extract an agent profile dict from a stored AgentRecord for simulation."""
    profile = record.get("profile", {})
    # Ensure required fields exist for the simulator
    if "type" not in profile:
        profile["type"] = "consumer"
    if "id" not in profile:
        profile["id"] = record.get("agent_id", "unknown")
    if "name" not in profile:
        profile["name"] = profile.get("id", "unknown")
    # Merge persistence metadata into profile
    profile["_from_store"] = True
    profile["_task_count"] = record.get("task_count", 0)
    return profile


def _convert_user_product(user_product: dict) -> dict:
    """Convert user-provided product description to product_directions format."""
    target = user_product.get("target_market", "consumer")
    # Infer category from target_market
    category_map = {"consumer": "consumer_app", "smb": "B2B_saas", "enterprise": "B2B_saas"}
    category = user_product.get("category", category_map.get(target, "consumer_app"))

    return {
        "id": user_product.get("id", f"user-prod-{hashlib.md5(user_product.get('name', 'product').encode()).hexdigest()[:4]}"),
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


def _load_seed_data(seed_data: dict = None, seed_source: str = None) -> dict:
    """Load seed data from user-provided dict, gold snapshot, or default JSON files.

    Priority: seed_data param > seed_source path > default static JSON files.
    """
    if seed_data:
        # If seed_data has 'dimensions' key (gold snapshot format), unwrap it
        if "dimensions" in seed_data:
            return seed_data
        return seed_data

    # Try loading from gold snapshot
    if seed_source:
        try:
            with open(seed_source, encoding="utf-8") as f:
                snapshot = json.load(f)
            # If snapshot has dimensions, use full snapshot (pipeline will unwrap)
            if "dimensions" in snapshot:
                print(f"  [SEED] Loaded gold snapshot: {seed_source} "
                      f"({len(snapshot.get('dimensions', {}))} dimensions)", flush=True)
                return snapshot
            # Otherwise treat as raw seed dict
            return snapshot
        except FileNotFoundError:
            print(f"  [WARN] Gold snapshot not found: {seed_source}, falling back to static JSON", flush=True)
        except Exception as e:
            print(f"  [WARN] Failed to load seed source: {e}", flush=True)

    # Fallback: load legacy static JSON files
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
            user_product: dict = None, sim_rounds: int = None,
            agent_cap: int = None, seed_source: str = None,
            reuse_agents: bool = False, sample_strategy: str = "stratified") -> dict:
        """
        Run the MarketFish pipeline.

        Args:
            seed_data: Market seed data dict. If None, loads from seed_source or default JSON files.
            mode: "explore" (LLM generates directions),
                  "validate" (user injects product, skips idea_generator),
                  "hybrid" (user product + LLM-generated competitors)
            reuse_agents: If True, load agents from store instead of regenerating.
            user_product: Product dict for validate/hybrid modes.
                Schema: {name, description, target_market, pricing, [pain_point, differentiation]}
            sim_rounds: Override simulation rounds (default: from config).
            agent_cap: Override consumer agent cap (default: from config).
            seed_source: Path to gold seed_snapshot.json (new ingestion pipeline).

        Returns:
            Pipeline result dict with stages, product_directions, and final_report.
        """
        start_time = time.time()
        mode_label = {"explore": _t("pipeline.explore_label"), "validate": _t("pipeline.validate_label"), "hybrid": _t("pipeline.hybrid_label")}.get(mode, mode)
        output = {"pipeline_version": "2.0", "input_mode": mode, "stages": {}}

        # Apply random seed for reproducibility
        rng_seed = _sim_cfg().get("random_seed", 42)
        if rng_seed:
            random.seed(rng_seed)
            output["random_seed"] = rng_seed

        # Load seed data — supports gold snapshot or legacy static JSON
        seed = _load_seed_data(seed_data, seed_source)

        # If seed is a gold snapshot (has 'dimensions' key), extract dimensions
        if "dimensions" in seed and "snapshot_id" in seed:
            output["seed_source"] = "gold_snapshot"
            output["seed_snapshot_id"] = seed.get("snapshot_id", "unknown")
            # Pass the full snapshot through — ontology will use dimensions
            print(f"  [SEED] Using gold snapshot: {seed.get('snapshot_id', '?')}", flush=True)

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
            agents_from_store = 0
            agents = []

            if reuse_agents:
                # v6: Load agents from persistent store instead of regenerating
                try:
                    from engine.agent_store import AgentStore
                    store = AgentStore()
                    pool_size = store.count()
                    target = agent_cap or _pcfg()["agent_consumer_cap"]
                    if pool_size > 0:
                        agents = store.sample(target_count=target, strategy=sample_strategy)
                        # Extract profile from stored records for the simulator
                        agents = [_extract_sim_agent(r) for r in agents]
                        agents_from_store = len(agents)
                        print(f"  [STAGE 3/5] Agents loaded from store: {agents_from_store}/{target} (pool: {pool_size})", flush=True)
                except Exception as e:
                    print(f"  [STAGE 3/5] Agent store load failed: {e}, falling back to generation", flush=True)

            if agents_from_store == 0:
                print("  [STAGE 3/5] Agent Generation...", flush=True)
                placeholder_dirs = [{"id": "placeholder", "name": "Placeholder — real directions generated in 3b"}]
                agents_data = generate_agents(knowledge_graph, placeholder_dirs)
                agents = agents_data.get("agents", [])
                output["stages"]["agents"] = {"status": "ok", "count": len(agents), "source": "llm"}
            else:
                output["stages"]["agents"] = {"status": "ok", "count": len(agents), "source": "store", "pool_size": store.count()}

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
            # Skip if agents loaded from store (they're direction-agnostic)
            if not reuse_agents or agents_from_store == 0:
                self.status = "stage3b_agents_v2"
                agents_data = generate_agents(knowledge_graph, product_directions)
                agents = agents_data.get("agents", [])
                output["stages"]["agents_v2"] = {"status": "ok", "count": len(agents), "source": "llm"}
            else:
                output["stages"]["agents_v2"] = {"status": "ok", "count": len(agents), "source": "store"}

            # Stage 4: Market Simulation
            self.status = "stage4_simulation"
            print("  [STAGE 4/5] Market Simulation (30 rounds, coupling + RL)...", flush=True)
            all_results = []
            coupling_stats = {}
            rl_stats = {}
            all_sim_results = []  # v6: collect all sim_results for agent persistence
            output["stages"]["simulation"] = {"sim_log": []}

            _market_config = _cfg()["market_types"]
            market_types = []
            # Apply agent cap override if specified
            consumer_cap = agent_cap or _pcfg()["agent_consumer_cap"]
            for m in _market_config:
                if m == "b2c":
                    market_types.append((m, [a for a in agents if a.get("type") == "consumer"][:consumer_cap]))
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
                    rounds=sim_rounds or _cfg()["simulation_rounds"],
                    market_type=market_type,
                )
                all_results.extend(sim_result.get("results", []))
                all_sim_results.append(sim_result)  # v6: collect for agent persistence

                # Save simulation log for post-hoc evidence extraction
                output["stages"]["simulation"]["sim_log"].extend(sim_result.get("log", []))

                if sim_result.get("coupling_history"):
                    coupling_stats[market_type] = {
                        "rounds": len(sim_result["coupling_history"]),
                        "final_sentiment": sim_result["coupling_history"][-1]["market_signals"]["avg_sentiment"] if sim_result["coupling_history"] else 0,
                    }
                if sim_result.get("rl_summary"):
                    rl_stats[market_type] = sim_result["rl_summary"]

            output["stages"]["simulation"].update({
                "status": "ok",
                "markets_simulated": len(market_types),
                "total_results": len(all_results),
                "cross_domain_coupling": coupling_stats,
                "economic_alignment_rl": rl_stats,
                "_sim_results": all_sim_results,  # v6: for agent persistence merge
            })
            self.stages_completed.append("simulation")

            # v6: Persist agents after simulation — merge all market agent_states
            self.status = "stage4b_persist"
            task_id = user_product.get("name", mode) if user_product else mode
            try:
                from engine.agent_store import AgentStore
                store = AgentStore()
                # Collect agent_states from all sim_results (one per market type)
                all_sim_results = output["stages"]["simulation"].get("_sim_results", [])
                merged_states = {}
                for sr in all_sim_results:
                    merged_states.update(sr.get("agent_states", {}))
                # Fallback: if _sim_results not collected, use last sim_result
                if not merged_states and "agent_states" in sim_result:
                    merged_states = sim_result["agent_states"]
                saved = store.save_batch(merged_states, task_id=task_id)
                pool = store.count()
                print(f"  [STORE] {saved} agents persisted (pool: {pool} total)", flush=True)
                output["stages"]["agent_store"] = {"status": "ok", "saved": saved, "pool_size": pool}
            except Exception as e:
                print(f"  [STORE] Persist skipped: {e}", flush=True)
                output["stages"]["agent_store"] = {"status": "skipped", "reason": str(e)}

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
