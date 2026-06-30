"""
Stage 3a: Agent Generation — Batch-parallel for scale.
Target: 100+ agents (75 consumer + 25 SMB + 10 enterprise + 10 competitor/env).

Strategy: Split into N parallel LLM calls, each generating ~25 agents.
This avoids single-call token limits and LLM "lazy generation" (12 instead of 100).
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from engine.llm_client import get_llm
from engine.network import build_agent_network
from engine.config import agent_gen_cfg as _cfg, agent_batches as _batches

BATCH_PROMPT = """You are generating market agents for a simulation. Generate EXACTLY the requested number of agents with diverse, realistic profiles.

Output EXACTLY this JSON:
{
  "agents": [
    {
      "id": "unique_slug_with_number",
      "type": "consumer|smb|enterprise|competitor|environment",
      "name": "readable Chinese name",
      "demographics": { "age": "range", "income_cny": "range", "city_tier": "1-5", "occupation": "specific job" },
      "bdi": {
        "beliefs": ["2-3 specific beliefs about AI, money, technology"],
        "desires": ["2-3 concrete goals"],
        "intentions": ["1-2 immediate next actions"]
      },
      "budget_monthly_cny": "specific number",
      "pain_points": ["3-5 ranked by severity, very specific"],
      "tech_savviness": 0.0-1.0,
      "decision_speed": "impulse|days|weeks|months",
      "influence_weight": 0.0-3.0,
      "social_network": {
        "connections": [],
        "network_type": "small_world"
      }
    }
  ]
}

MANDATORY:
- Generate EXACTLY the number of agents specified in the prompt. No fewer.
- Every agent must have a DIFFERENT occupation, different income, different pain points.
- Use realistic 2026 China contexts: consumption downgrade, OPC (one-person-company) boom, AI everywhere, WeChat ecosystem.
- Budgets in CNY must be realistic for the agent's income level.
"""

# Batch definitions — lazy-loaded from config/defaults.yaml
def _get_batches():
    return _batches()


def _generate_one_batch(batch_def: dict, knowledge_graph: dict, product_directions: list) -> list:
    """Generate one batch of agents via LLM. Returns list of agent dicts."""
    llm = get_llm()

    user_prompt = f"""Generate EXACTLY {batch_def['count']} {batch_def['agent_type']} agents.

BATCH LABEL: {batch_def['label']}
DIVERSITY REQUIREMENT: {batch_def['diversity']}

KNOWLEDGE GRAPH CONTEXT:
{json.dumps(knowledge_graph, indent=2, ensure_ascii=False)[:_cfg()["context_kg_chars"]]}

PRODUCT DIRECTIONS (agents will evaluate these):
{json.dumps(product_directions, indent=2, ensure_ascii=False)[:_cfg()["context_ideas_chars"]]}

CRITICAL: Generate EXACTLY {batch_def['count']} agents. Each with different occupation, income, pain points.
Use realistic 2026 China data. IDs must be unique slugs."""

    try:
        result = llm.chat_json(
            system=BATCH_PROMPT,
            user=user_prompt,
            agent_type=batch_def["agent_type"],
            temperature=_cfg()["temperature"],
        )
        agents = result.get("agents", [])
        # Tag with batch label
        for a in agents:
            a["batch_label"] = batch_def["label"]
        print(f"  [BATCH] {batch_def['label']}: generated {len(agents)}/{batch_def['count']} {batch_def['agent_type']}s", flush=True)
        return agents
    except Exception as e:
        print(f"  [BATCH FAIL] {batch_def['label']}: {e}", flush=True)
        return []


def generate_agents(knowledge_graph: dict, product_directions: list[dict]) -> dict:
    """Stage 3a: Generate 100+ agents via parallel batch LLM calls."""
    print(f"  [AGENT] Generating agents in {len(_get_batches())} parallel batches...", flush=True)

    all_agents = []
    failures = 0

    with ThreadPoolExecutor(max_workers=min(_cfg()["max_workers"], len(_get_batches()))) as executor:
        futures = {
            executor.submit(_generate_one_batch, batch, knowledge_graph, product_directions): batch["label"]
            for batch in _get_batches()
        }
        for future in as_completed(futures):
            label = futures[future]
            try:
                agents = future.result(timeout=_cfg()["batch_timeout"])
                all_agents.extend(agents)
            except Exception as e:
                print(f"  [BATCH TIMEOUT] {label}: {e}", flush=True)
                failures += 1

    # Deduplicate by ID
    seen_ids = set()
    unique_agents = []
    for a in all_agents:
        aid = a.get("id", "")
        if aid and aid not in seen_ids:
            seen_ids.add(aid)
            unique_agents.append(a)

    # Validate diversity
    types = {}
    for a in unique_agents:
        t = a.get("type", "unknown")
        types[t] = types.get(t, 0) + 1

    print(f"  [AGENT] Total: {len(unique_agents)} agents ({len(all_agents)} raw, {failures} batch failures)", flush=True)
    for t, c in sorted(types.items()):
        print(f"    {t}: {c}", flush=True)

    # Minimum check
    consumer_count = types.get("consumer", 0)
    smb_count = types.get("smb", 0)
    if consumer_count < _cfg()["min_consumers_warn"]:
        print(f"  [WARN] Only {consumer_count} consumers — minimum 30 recommended", flush=True)
    if smb_count < _cfg()["min_smb_warn"]:
        print(f"  [WARN] Only {smb_count} SMBs — minimum 10 recommended", flush=True)

    result = {"agents": unique_agents}

    # Apply small-world network topology
    result["agents"] = build_agent_network(result["agents"])
    from engine.network import network_stats
    stats = network_stats(result["agents"])
    print(f"  [NET] Small-world: {stats['agents']} agents, {stats['total_edges']} edges, avg degree {stats['avg_degree']}", flush=True)

    return result
