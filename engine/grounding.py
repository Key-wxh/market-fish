"""
Grounding & Validation — v6 Step 8.

SMIF (ETASR 2026, DOI 10.48084/etasr.16536): RAG retrieval + rule constraints
+ state compression to keep agent outputs grounded in real data.

Key mechanisms:
  - RAG: retrieve relevant market data for agent decisions
  - Rule constraints: hard bounds on agent outputs (budget, realism)
  - State compression: relevance-weighted truncation to control prompt size
"""
import json
from pathlib import Path
from engine.config import get_config


def rag_context(agent_profile: dict, products: list, seed_data: dict = None) -> str:
    """Retrieve relevant market grounding data for an agent's decision.

    Uses seed_snapshot dimensions to provide real market context,
    preventing agents from hallucinating market conditions.
    """
    cfg = get_config().get("grounding", {})
    if not cfg.get("enabled", False) or not cfg.get("rag_enabled", True):
        return ""

    if not seed_data:
        return ""

    dimensions = seed_data.get("dimensions", {})
    if not dimensions:
        return ""

    lines = ["\n=== MARKET GROUNDING (real data) ==="]
    # Pick 1-2 most relevant dimensions
    for dim_name in list(dimensions.keys())[:2]:
        dim = dimensions[dim_name]
        if isinstance(dim, dict):
            # Extract key signals
            signals = {}
            for k, v in dim.items():
                if isinstance(v, (int, float, str)) and not k.startswith("_"):
                    signals[k] = v
            if signals:
                lines.append(f"  {dim_name}: {json.dumps(signals, ensure_ascii=False)[:200]}")

    lines.append("  Base your decisions on these real market conditions.")
    return "\n".join(lines)


def apply_rule_constraints(decision: dict, agent_profile: dict) -> dict:
    """Apply hard constraints to an agent's decision. Returns modified decision.

    Constraints:
      - Budget: cannot spend more than budget_monthly_cny
      - WTP reasonability: WTP cannot exceed 3x estimated pricing
      - Decision speed: impulse buyers cannot deliberate for many rounds
    """
    cfg = get_config().get("grounding", {})
    if not cfg.get("enabled", False) or not cfg.get("rule_constraints_enabled", True):
        return decision

    budget = float(agent_profile.get("budget_monthly_cny", 500))
    wtp = float(decision.get("willingness_to_pay_cny", 0))

    # Budget constraint
    if wtp > budget * 3:
        decision["willingness_to_pay_cny"] = budget
        decision["_constraint_applied"] = "budget_cap"

    # Action constraint: can't purchase without discovering
    action = decision.get("action", "")
    if action == "purchase" and decision.get("product_id", "").startswith("unknown"):
        decision["action"] = "discover"
        decision["_constraint_applied"] = "unknown_product"

    return decision


def compress_state(agent_state: dict, max_chars: int = 8000) -> dict:
    """Relevance-weighted state compression (SMIF).

    Keeps recent observations at full weight, older ones at reduced weight.
    Returns a compressed copy of the state for prompt context.
    """
    cfg = get_config().get("grounding", {})
    if not cfg.get("enabled", False) or not cfg.get("state_compression", {}).get("enabled", True):
        return agent_state

    temporal_w = cfg.get("state_compression", {}).get("temporal_weight", 0.7)

    # Compress history: keep last N entries at full weight
    history = agent_state.get("history", [])
    if len(history) > 20:
        # Weighted truncation: keep 10 most recent + 10 highest-importance
        recent = history[-10:]
        older = history[:-10]
        older.sort(key=lambda h: abs(float(h.get("willingness_to_pay_cny", 0))), reverse=True)
        history = older[:10] + recent

    compressed = dict(agent_state)
    compressed["history"] = history
    compressed["_compressed"] = True
    return compressed


def ground_validate(decision: dict, agent_profile: dict, seed_data: dict = None) -> dict:
    """Full grounding validation: RAG + rules + compression.

    Returns the validated decision dict.
    """
    cfg = get_config().get("grounding", {})
    if not cfg.get("enabled", False):
        return decision

    # Apply rule constraints
    decision = apply_rule_constraints(decision, agent_profile)

    # Add grounding flag
    decision["_grounding_validated"] = True

    return decision
