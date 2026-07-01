"""
Stage 3a: Agent Generation — Batch-parallel for scale.
Target: 100+ agents (75 consumer + 25 SMB + 10 enterprise + 10 competitor/env).

Strategy: Split into N parallel LLM calls, each generating ~25 agents.
This avoids single-call token limits and LLM "lazy generation" (12 instead of 100).

Language-aware: agent names follow the current UI language (zh → Chinese, en → English).
"""
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from engine.llm_client import get_llm
from engine.network import build_agent_network
from engine.config import agent_gen_cfg as _cfg, agent_batches as _batches
from engine.i18n import get_lang

def _name_instruction() -> str:
    """Return the name field instruction for the current language."""
    if get_lang() == "en":
        return '"name": "English name — first name + last name for people, business name for shops, e.g. \'Alice Chen\', \'Bob\'s Noodle House\' — NO Chinese characters, NO pinyin in parentheses"'
    else:
        return '"name": "纯中文姓名 — 人名或店铺名，例如\'王丽\'\'张伟\'\'李记面馆\' — 不含英文、拼音、括号翻译"'

def _clean_name(name: str) -> str:
    """Post-process agent name: strip parenthetical translations based on language."""
    if get_lang() == "en":
        # Strip Chinese parenthetical: "Alice Chen (陈丽)" → "Alice Chen"
        return re.sub(r'\s*\([^)]*[一-鿿][^)]*\)\s*$', '', name).strip()
    else:
        # Strip English/pinyin parenthetical: "王美美 (Wang Meimei)" → "王美美"
        return re.sub(r'\s*\([^)]*[a-zA-Z][^)]*\)\s*$', '', name).strip()

BATCH_PROMPT_ZH = """You are generating market agents for a Chinese-market simulation. Generate EXACTLY the requested number of agents with diverse, realistic profiles.

Output EXACTLY this JSON:
{
  "agents": [
    {
      "id": "unique_slug_with_number",
      "type": "consumer|smb|enterprise|competitor|environment",
      {name_field},
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
- Names, beliefs, desires, pain_points, occupation: ALL must be Chinese ONLY — no English, no pinyin, no parenthetical translations. Pure Chinese text throughout.
"""

BATCH_PROMPT_EN = """You are generating market agents for a simulation. Generate EXACTLY the requested number of agents with diverse, realistic profiles.

Output EXACTLY this JSON:
{
  "agents": [
    {
      "id": "unique_slug_with_number",
      "type": "consumer|smb|enterprise|competitor|environment",
      {name_field},
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
- Names, beliefs, desires, pain_points, occupation: ALL must be English ONLY — no Chinese characters, no pinyin in parentheses. Pure English text throughout.
"""

def _build_prompt() -> str:
    """Build the language-appropriate batch prompt."""
    name_instr = _name_instruction()
    if get_lang() == "en":
        return BATCH_PROMPT_EN.replace("{name_field}", name_instr)
    else:
        return BATCH_PROMPT_ZH.replace("{name_field}", name_instr)


# Batch definitions — lazy-loaded from config/defaults.yaml
def _get_batches():
    return _batches()


def _generate_one_batch(batch_def: dict, knowledge_graph: dict, product_directions: list) -> list:
    """Generate one batch of agents via LLM. Returns list of agent dicts with cleaned names."""
    llm = get_llm()
    lang = get_lang()

    user_prompt = f"""Generate EXACTLY {batch_def['count']} {batch_def['agent_type']} agents.

BATCH LABEL: {batch_def['label']}
DIVERSITY REQUIREMENT: {batch_def['diversity']}
LANGUAGE: {"English only" if lang == "en" else "Chinese only"}

KNOWLEDGE GRAPH CONTEXT:
{json.dumps(knowledge_graph, indent=2, ensure_ascii=False)[:_cfg()["context_kg_chars"]]}

PRODUCT DIRECTIONS (agents will evaluate these):
{json.dumps(product_directions, indent=2, ensure_ascii=False)[:_cfg()["context_ideas_chars"]]}

CRITICAL: Generate EXACTLY {batch_def['count']} agents. Each with different occupation, income, pain points.
Use realistic 2026 China data. IDs must be unique slugs."""

    max_retries = _cfg().get("batch_retries", 2)
    last_error = None

    for attempt in range(max_retries):
        try:
            result = llm.chat_json(
                system=_build_prompt(),
                user=user_prompt,
                agent_type=batch_def["agent_type"],
                temperature=_cfg()["temperature"],
            )
            agents = result.get("agents", [])
            # Tag with batch label + clean names
            cleaned = 0
            for a in agents:
                a["batch_label"] = batch_def["label"]
                original = a.get("name", "")
                a["name"] = _clean_name(original)
                if a["name"] != original:
                    cleaned += 1
            if cleaned:
                print(f"  [BATCH] {batch_def['label']}: cleaned {cleaned} bilingual names", flush=True)
            print(f"  [BATCH] {batch_def['label']}: generated {len(agents)}/{batch_def['count']} {batch_def['agent_type']}s", flush=True)
            return agents
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                import time
                wait = 2 ** attempt  # exponential backoff: 1s, 2s
                print(f"  [BATCH RETRY] {batch_def['label']}: attempt {attempt+1} failed ({e}) — retrying in {wait}s...", flush=True)
                time.sleep(wait)
                continue

    print(f"  [BATCH FAIL] {batch_def['label']}: {last_error} (after {max_retries} attempts)", flush=True)
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
