"""
Stage 3b: Product Direction Generation.
LLM analyzes knowledge graph → finds pain point spaces → generates novel product directions.
THIS is the prediction engine. These directions don't exist in any existing product library.
"""

import json
from engine.llm_client import get_llm

IDEA_SYSTEM_PROMPT = """You are a product strategist. Given a market knowledge graph with identified pain point spaces, generate NOVEL product directions that don't currently exist in the market.

Each direction must solve a pain point in the graph where demand exists but supply is weak or missing.

Output EXACTLY this JSON:
{
  "product_directions": [
    {
      "id": "prod-001",
      "name": "catchy one-line description",
      "category": "B2C_tool|B2B_saas|consumer_app|browser_extension|cli_tool|mini_program|open_source",
      "target_market": "consumer|smb|enterprise",
      "pain_point_addressed": "which specific pain from the knowledge graph",
      "why_graph_shows_opportunity": "what signals indicate demand + supply gap",
      "estimated_pricing_cny": "range",
      "technical_feasibility": 0.0-1.0,
      "viral_potential": 0.0-1.0,
      "key_risks": ["what could go wrong"],
      "similar_existing": "closest existing product (if any) — prove this is NOT a copy"
    }
  ]
}

RULES:
- Generate 5-8 directions. Each must be genuinely novel — not a copy of existing products.
- Focus on 2026 China market reality: consumption downgrade, AI cost collapse, WeChat ecosystem dominance, OPC boom.
- Prioritize directions with high viral potential (shareable results, controversial names, social proof).
- Every direction must reference specific pain point spaces from the knowledge graph.
- AI-first: every direction must leverage AI in a way that wasn't possible before 2026.
"""


def generate_product_directions(knowledge_graph: dict) -> list[dict]:
    """Stage 3b: Generate novel product directions from pain point spaces."""
    llm = get_llm()

    # Focus on pain point spaces
    pain_spaces = knowledge_graph.get("pain_point_spaces", [])
    if not pain_spaces:
        raise ValueError("Knowledge graph has no pain_point_spaces")

    user_prompt = f"""Generate novel product directions based on these pain point spaces.

PAIN POINT SPACES (where demand > supply):
{json.dumps(pain_spaces, indent=2, ensure_ascii=False)}

MARKET ENTITIES:
{json.dumps(knowledge_graph.get('entities', [])[:10], indent=2, ensure_ascii=False)}

2026 CONTEXT: China consumption downgrade. AI costs collapsed 90%. WeChat 1B+ users. OPC 16M+.
Consumer apps going viral with controversial names (死了么). Solo devs getting funded from GitHub trending.

Generate product directions that could succeed in THIS environment. Not generic ideas — specific, novel directions that leverage current technology and market conditions."""

    result = llm.chat_json(system=IDEA_SYSTEM_PROMPT, user=user_prompt)

    if "product_directions" not in result:
        raise ValueError("Missing product_directions in output")

    return result["product_directions"]
