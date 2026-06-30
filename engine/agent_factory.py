"""
Stage 3a: Agent Generation — 3-market coverage (B2C + SMB + Enterprise).
MiroFish OasisProfileGenerator pattern + TwinMarket BDI architecture.
"""

import json
from engine.llm_client import get_llm

AGENT_SYSTEM_PROMPT = """You generate realistic market agents from a knowledge graph. Each agent must have a BDI (Belief-Desire-Intention) cognitive model for decision-making.

Output EXACTLY this JSON:
{
  "agents": [
    {
      "id": "unique_slug",
      "type": "consumer|smb|enterprise|competitor|environment",
      "name": "readable name",
      "demographics": { "age": "range", "income_cny": "range", "city_tier": "1-5" },
      "bdi": {
        "beliefs": ["what they believe about the market/value/technology"],
        "desires": ["what they want to achieve"],
        "intentions": ["what they plan to do next"]
      },
      "budget_monthly_cny": "specific number or range",
      "pain_points": ["ranked by severity"],
      "tech_savviness": 0.0-1.0,
      "decision_speed": "impulse|days|weeks|months",
      "influence_weight": 0.0-3.0,
      "social_network": {
        "connections": ["other_agent_ids they are connected to"],
        "network_type": "small_world|hub|isolated"
      },
      "activity_pattern": {
        "active_hours": "e.g. 9-23 for consumers, 9-18 for enterprise",
        "decision_frequency": "daily|weekly|monthly"
      }
    }
  ]
}

RULES:
- Consumer agents: 50-80. Diverse demographics. Include impulse buyers AND rational buyers.
- SMB agents: 30-50. Different industries (restaurant/retail/beauty/education).
- Enterprise agents: 5-15. Include procurement process details.
- Competitor agents: 5-15. Existing solutions with market share.
- Environment agents: 3-5. Economic/policy/tech trend agents.
- Use SMALL WORLD network topology (UChicago 2025: best balance of diffusion speed vs diversity).
- BDI beliefs must reflect the economic reality of 2026 China (consumption downgrade, OPC boom, AI cost collapse).
"""


def generate_agents(knowledge_graph: dict, product_directions: list[dict]) -> dict:
    """Stage 3a: Generate market agents from knowledge graph."""
    llm = get_llm()

    user_prompt = f"""Generate a full set of market agents from this knowledge graph.

KNOWLEDGE GRAPH:
{json.dumps(knowledge_graph, indent=2, ensure_ascii=False)[:6000]}

PRODUCT DIRECTIONS TO EVALUATE:
{json.dumps(product_directions, indent=2, ensure_ascii=False)[:2000]}

Generate agents that can realistically evaluate these product directions.
Remember: heterogeneous agents (Machine Spirits 2026 principle), BDI cognitive model, small-world network topology."""

    result = llm.chat_json(system=AGENT_SYSTEM_PROMPT, user=user_prompt, agent_type="smb")

    if "agents" not in result:
        raise ValueError("Agent generation missing 'agents' field")

    # Validate minimum agent diversity — warn but don't block on missing types
    types = set(a["type"] for a in result["agents"])
    required = {"consumer", "smb"}
    missing = required - types
    if missing:
        raise ValueError(f"Agent generation missing required types: {missing}")
    optional_missing = {"competitor", "enterprise", "environment"} - types
    if optional_missing:
        print(f"  [WARN] Missing optional agent types: {optional_missing}")

    return result
