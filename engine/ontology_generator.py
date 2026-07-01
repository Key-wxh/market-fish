"""
Stage 1: Ontology Generation — MiroFish OntologyGenerator pattern.
Feeds raw market signals → LLM extracts market participant types and decision factors.
"""

import json
from engine.llm_client import get_llm

ONTOLOGY_SYSTEM_PROMPT = """You are a market structure analyst. Given market signals across multiple validated dimensions (macroeconomic indicators, technology adoption trends, freelance demand data, B2B software market signals, consumer behavior, market sentiment, and more), identify the MARKET PARTICIPANT TYPES and DECISION FACTORS that define the market structure.

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
- Budget ranges must be realistic CNY amounts aligned with current economic conditions.
- pain_points must be concrete, not abstract.
- Use ALL provided data dimensions — don't focus on just one or two.
"""


def generate_ontology(seed_data: dict) -> dict:
    """Stage 1: Generate market ontology from seed signals.

    Source-agnostic: iterates over ALL keys in seed_data, whether they come
    from the old static JSON files or the new gold snapshot dimensions.
    """
    llm = get_llm()

    # Skip metadata keys (_dimensions, _signals, _provenance, _meta, _snapshot_id)
    skip_keys = {"_dimensions", "_signals", "_provenance", "_meta", "_snapshot_id"}

    # Build prompt from all available data keys
    prompt_parts = []
    for key in sorted(seed_data.keys()):
        if key.startswith("_") or key in skip_keys:
            continue
        value = seed_data[key]
        if value:  # Skip empty dimensions
            label = key.replace("_", " ").title()
            prompt_parts.append(
                f"{label}:\n{json.dumps(value, indent=2, ensure_ascii=False)}"
            )

    if not prompt_parts:
        raise ValueError("No valid seed data dimensions found. Check seed_data input.")

    user_prompt = "Analyze these market signals and generate the ontology:\n\n"
    user_prompt += "\n\n".join(prompt_parts)
    user_prompt += "\n\nBased on ALL these signals across multiple dimensions, what are the REAL market participant types, relationships, and decision factors?\nRemember: concrete, quantified, specific. Not generic labels. Use ALL available data dimensions."

    result = llm.chat_json(system=ONTOLOGY_SYSTEM_PROMPT, user=user_prompt, agent_type="ontology")

    # Validate required fields
    if "participant_types" not in result:
        raise ValueError("Ontology missing participant_types")
    if len(result["participant_types"]) < 8:
        raise ValueError(f"Expected >= 8 participant types, got {len(result['participant_types'])}")

    return result
