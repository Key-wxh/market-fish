"""
Stage 2: Knowledge Graph Construction — MiroFish GraphRAG pattern.
Builds a market knowledge graph from ontology + seed signals.
Uses Neo4j for storage (MiroFish-ES offline fork validated).
"""

import json
from engine.llm_client import get_llm

GRAPH_SYSTEM_PROMPT = """You are a knowledge graph constructor. Given a market ontology and raw data, generate ENTITY INSTANCES and RELATIONSHIPS that form a market map.

Output EXACTLY this JSON:
{
  "entities": [
    {
      "id": "unique_slug",
      "type": "one of the participant_type names from ontology",
      "name": "readable name",
      "attributes": {
        "budget_monthly_cny": "specific range or number",
        "pain_points": ["concrete problems"],
        "decision_speed": "impulse|days|weeks|months",
        "tech_savviness": 0.0-1.0,
        "influence_weight": 0.0-3.0,
        "market_size_estimate": "how many similar entities exist"
      }
    }
  ],
  "relationships": [
    {
      "from": "entity_id",
      "to": "entity_id",
      "type": "relationship_type from ontology",
      "strength": 0.0-1.0,
      "description": "explain the relationship"
    }
  ],
  "pain_point_spaces": [
    {
      "name": "descriptive name",
      "description": "what specific pain is under-served",
      "demand_strength": 0.0-1.0,
      "supply_gap": 0.0-1.0,
      "estimated_monthly_spend_cny": "range",
      "related_entity_ids": ["entities with this pain"]
    }
  ]
}

RULES:
- Generate 20-30 entity instances (mix of consumers, SMBs, enterprises, suppliers).
- Generate 15-25 relationships connecting them.
- Generate 5-10 pain_point_spaces — areas where demand exists but supply is weak or missing.
- Use specific CNY amounts, not vague ranges.
- Reference real data from the seed signals.
"""


def build_knowledge_graph(ontology: dict, seed_data: dict) -> dict:
    """Stage 2: Build market knowledge graph."""
    llm = get_llm()

    user_prompt = f"""Build a knowledge graph from this ontology and seed data.

ONTOLOGY:
{json.dumps(ontology, indent=2, ensure_ascii=False)}

MARKET SIGNALS:
{json.dumps(seed_data, indent=2, ensure_ascii=False)[:8000]}

Create concrete entity instances and relationships. Focus especially on PAIN POINT SPACES — where is demand strong but supply weak?"""

    result = llm.chat_json(system=GRAPH_SYSTEM_PROMPT, user=user_prompt)

    if "entities" not in result or "pain_point_spaces" not in result:
        raise ValueError("Graph missing required fields (entities/pain_point_spaces)")

    return result
