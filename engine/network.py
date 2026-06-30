"""
Small-World Network Topology — UChicago Innovation 2025 principle.
Key finding: fully-connected networks converge too early (kill diversity).
Ring networks preserve diversity but diffuse too slowly.
Small-world (Watts-Strogatz model) balances both — optimal for innovation diffusion.

v2: Uses actual agent IDs (not synthetic indices). Works with batch-generated agents.
"""

import random
import math
from engine.config import network_cfg as _cfg


def watts_strogatz_network(n: int, k: int, beta: float) -> list[dict]:
    """
    Build Watts-Strogatz small-world network.

    Args:
        n: Number of agents
        k: Each agent connects to k nearest neighbors (must be even, k < n)
        beta: Rewiring probability. 0=ring, 1=random. 0.1=small-world (optimal per UChicago)

    Returns:
        List of agent connections by index: [{"idx": 0, "connections": [1, 2, ...]}, ...]
    """
    if k % 2 != 0:
        k += 1
    if k >= n:
        k = n - 2 if n > 2 else max(1, n - 1)
    if k < 2:
        k = 2

    # Step 1: Ring lattice — connect to k/2 neighbors on each side
    connections = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(1, k // 2 + 1):
            left = (i - j) % n
            right = (i + j) % n
            connections[i].add(left)
            connections[i].add(right)

    # Step 2: Rewire with probability beta (small-world: beta ≈ 0.1)
    for i in range(n):
        for j in range(1, k // 2 + 1):
            if random.random() < beta:
                old_neighbor = (i + j) % n
                if old_neighbor in connections[i]:
                    connections[i].discard(old_neighbor)
                    candidates = [x for x in range(n) if x != i and x not in connections[i]]
                    if candidates:
                        new_neighbor = random.choice(candidates)
                        connections[i].add(new_neighbor)

    return [{"idx": i, "connections": list(conns)}
            for i, conns in connections.items()]


def assign_network_to_agents(agents: list, network: list) -> list:
    """
    Assign small-world network connections to agent profiles.
    Maps network indices to actual agent IDs.
    """
    # Map index -> actual agent ID
    id_map = {i: agents[i]["id"] for i in range(len(agents))}

    for node in network:
        idx = node["idx"]
        if idx < len(agents):
            agents[idx]["social_network"] = {
                "connections": [id_map[c] for c in node["connections"] if c in id_map],
                "network_type": "small_world",
            }
    return agents


def build_agent_network(agents: list) -> list:
    """
    One-shot: build small-world network using actual agent IDs.
    beta=_cfg()["beta"] is the optimal value from UChicago research.
    """
    n = len(agents)
    if n <= 1:
        return agents

    # Each agent connects to ~k neighbors. Scale k with network size.
    k = max(_cfg()["k_min"], min(_cfg()["k_max"], n // _cfg()["k_divisor"]))
    network = watts_strogatz_network(n, k, beta=_cfg()["beta"])
    return assign_network_to_agents(agents, network)


def network_stats(agents: list) -> dict:
    """Compute network statistics for verification."""
    n = len(agents)
    total_conns = sum(len(a.get("social_network", {}).get("connections", [])) for a in agents)
    edges = total_conns / 2
    avg_degree = total_conns / n if n > 0 else 0
    return {
        "agents": n,
        "total_edges": int(edges),
        "avg_degree": round(avg_degree, 1),
        "type": "small_world",
    }
