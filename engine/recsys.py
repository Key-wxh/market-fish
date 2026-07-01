"""
Recommendation System — v6 Step 5.

OASIS (2025, arxiv 2411.11581): Agents see products through a recommendation
system, not randomly. Two modes:
  - hot_score: time-decayed popularity ranking (creates rich-get-richer dynamics)
  - interest_based: match products to agent's BDI/pain_points
"""
import math
from engine.config import get_config


def hot_score(product: dict, current_round: int, alpha: float = 0.015) -> float:
    """Hacker News-style hot score with time decay.

    Hot products rise to top, old products decay.
    alpha=0.015 halves heat every ~2 weeks in real time, here mapped to rounds.
    """
    base = product.get("adoption_count", 0) + product.get("purchaser_count", 0) + 1
    # Simulate "post age" — products introduced earlier have lower recency
    intro_round = product.get("intro_round", 1)
    age = max(1, current_round - intro_round)
    return math.log(base + 1) / (age ** alpha)


def interest_match(product: dict, agent_profile: dict) -> float:
    """Score how well a product matches an agent's interests.

    Uses agent BDI (beliefs/desires/pain_points) vs product description.
    Simple keyword overlap for now.
    """
    bdi = agent_profile.get("bdi", {})
    pain_points = " ".join(agent_profile.get("pain_points", []))
    beliefs = " ".join(bdi.get("beliefs", []))
    desires = " ".join(bdi.get("desires", []))

    agent_text = f"{pain_points} {beliefs} {desires}".lower()
    product_text = " ".join([
        product.get("name", ""),
        product.get("pain_point_addressed", ""),
        product.get("category", ""),
    ]).lower()

    if not agent_text or not product_text:
        return 0.5

    agent_words = set(agent_text.split())
    product_words = set(product_text.split())
    if not agent_words:
        return 0.5

    overlap = len(agent_words & product_words)
    return min(1.0, overlap / min(len(agent_words), 30))


def recommend(products: list[dict], agent_profile: dict, current_round: int,
              top_k: int = 5) -> list[dict]:
    """Recommend top-K products for an agent.

    Uses recsys config to determine mode (hot_score | interest_based).
    Falls back to original order if recsys disabled.
    """
    cfg = get_config().get("recsys", {})
    if not cfg.get("enabled", False):
        return products[:top_k]

    mode = cfg.get("type", "interest_based")
    alpha = cfg.get("hot_score_alpha", 0.015)

    scored = []
    for p in products:
        if mode == "hot_score":
            score = hot_score(p, current_round, alpha)
        else:  # interest_based
            score = interest_match(p, agent_profile)
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k]]


def recsys_filter(products: list[dict], agent_profiles: dict,
                  current_round: int = 1) -> dict[str, list[dict]]:
    """Filter products per agent through recommendation system.

    Returns {agent_id: [recommended products]}.
    """
    cfg = get_config().get("recsys", {})
    if not cfg.get("enabled", False):
        return {aid: products for aid in agent_profiles}

    recs_per_agent = {}
    for aid, profile in agent_profiles.items():
        recs_per_agent[aid] = recommend(products, profile, current_round,
                                        top_k=cfg.get("top_k_posts", 5))
    return recs_per_agent
