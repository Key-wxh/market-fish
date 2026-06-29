"""
Stage 1: Ontology Generation — MiroFish OntologyGenerator pattern.
Feeds raw market signals → LLM extracts market participant types and decision factors.
"""

import json
from engine.llm_client import get_llm

ONTOLOGY_SYSTEM_PROMPT = """You are a market structure analyst. Given raw market signals (freelancer demand data, economic indicators, technology trends), identify the MARKET PARTICIPANT TYPES and DECISION FACTORS that define the market structure.

Output EXACTLY this JSON schema:
{
  "participant_types": [
    {
      "name": "string",
      "category": "consumer|smb|enterprise|supplier|environment",
      "description": "who they are",
      "typical_budget_monthly_cny": "range",
      "pain_points": ["list"],
      "decision_speed": "impulse|days|weeks|months",
      "tech_savviness": 0.0-1.0,
      "influence_weight": 0.0-3.0
    }
  ],
  "relationship_types": [
    {
      "name": "string",
      "description": "pays_for|competes_with|depends_on|recommends|regulates|substitutes"
    }
  ],
  "decision_factors": [
    {
      "name": "string",
      "weight": 0.0-1.0,
      "description": "what drives purchase decisions"
    }
  ]
}

RULES:
- Generate EXACTLY 10 participant types. Include at least 3 consumer, 3 SMB, 1 enterprise, 2 supplier, 1 environment.
- Generate 8-10 relationship types.
- Generate 5-8 decision factors.
- Every participant type must have specific, quantified attributes — not generic labels.
- Budget ranges must be realistic CNY amounts aligned with China 2026 economic conditions.
- pain_points must be concrete, not abstract.
"""


def generate_ontology(seed_data: dict) -> dict:
    """Stage 1: Generate market ontology from seed signals."""
    llm = get_llm()

    # Format seed data for LLM consumption
    user_prompt = f"""Analyze these market signals and generate the ontology:

FREELANCER DEMAND DATA:
{json.dumps(seed_data.get('freelancer', {}), indent=2, ensure_ascii=False)}

ECONOMIC INDICATORS:
{json.dumps(seed_data.get('economy', {}), indent=2, ensure_ascii=False)}

TECHNOLOGY TRENDS:
{json.dumps(seed_data.get('tech', {}), indent=2, ensure_ascii=False)}

Based on these signals, what are the REAL market participant types, relationships, and decision factors?
Remember: concrete, quantified, specific. Not generic labels."""

    result = llm.chat_json(system=ONTOLOGY_SYSTEM_PROMPT, user=user_prompt)

    # Validate required fields
    if "participant_types" not in result:
        raise ValueError("Ontology missing participant_types")
    if len(result["participant_types"]) < 8:
        raise ValueError(f"Expected >= 8 participant types, got {len(result['participant_types'])}")

    return result
