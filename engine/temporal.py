"""
Temporal Activation Engine — v6 Step 4.

OASIS (2025, arxiv 2411.11581): Not all agents are active every round.
Realistic 24-hour activation probabilities simulate daily/weekly rhythms.
Inactive agents skip decisions (saving LLM cost) but social/emotional
contagion still affects them passively.
"""
import random
from engine.config import get_config


# Default 24-hour activation probabilities (sum ~1.0)
DEFAULT_ACTIVATION = [
    0.01, 0.005, 0.003, 0.005, 0.02, 0.05,   # 0-5时
    0.08, 0.10, 0.09, 0.07, 0.06, 0.05,       # 6-11时
    0.05, 0.04, 0.04, 0.05, 0.06, 0.07,       # 12-17时
    0.08, 0.07, 0.05, 0.03, 0.02, 0.015       # 18-23时
]


def get_activation_probs() -> list[float]:
    cfg = get_config().get("temporal", {})
    return cfg.get("activation_probabilities", DEFAULT_ACTIVATION)


def activate_agents(agent_ids: list[str], round_num: int,
                    rounds_total: int = 30) -> tuple[list[str], list[str]]:
    """Determine which agents are active this round.

    Maps simulation round to an hour of day (0-23), then samples activation
    based on that hour's probability.

    Returns:
        (active_ids, inactive_ids) — both lists of agent IDs.
        Inactive agents still receive passive social/emotional updates.
    """
    cfg = get_config().get("temporal", {})
    if not cfg.get("enabled", False):
        return agent_ids, []

    probs = get_activation_probs()
    # Map round to hour: spread rounds across 24h cycle
    hour = (round_num * 24 // max(rounds_total, 1)) % 24
    prob = probs[min(hour, 23)]

    random.seed(round_num * 1000)  # Deterministic per round
    active, inactive = [], []
    for aid in agent_ids:
        if random.random() < prob:
            active.append(aid)
        else:
            inactive.append(aid)

    return active, inactive
