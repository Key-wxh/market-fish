"""
Small-World Network Topology — UChicago Innovation 2025 principle.
Key finding: fully-connected networks converge too early (kill diversity).
Ring networks preserve diversity but diffuse too slowly.
Small-world (Watts-Strogatz model) balances both — optimal for innovation diffusion.

Implementation: Watts-Strogatz small-world network builder.
Agent social connections follow this topology for realistic information spread.
"""

import random
import math


def watts_strogatz_network(n: int, k: int, beta: float) -> list[dict]:
    """
    Build Watts-Strogatz small-world network.

    Args:
        n: Number of agents
        k: Each agent connects to k nearest neighbors (must be even, k < n)
        beta: Rewiring probability. 0=ring, 1=random. 0.1=small-world (optimal per UChicago)

    Returns:
        List of agent connections: [{"agent_id": "id", "connections": ["id1","id2",...]}, ...]
    """
    if k % 2 != 0:
        k += 1  # Must be even
    if k >= n:
        k = n - 2 if n > 2 else n - 1

    # Step 1: Create ring lattice — each agent connects to k/2 neighbors on each side
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
                # Remove one clockwise edge
                old_neighbor = (i + j) % n
                if old_neighbor in connections[i]:
                    connections[i].discard(old_neighbor)
                    # Rewire to random node (not self, not already connected)
                    candidates = [x for x in range(n) if x != i and x not in connections[i]]
                    if candidates:
                        new_neighbor = random.choice(candidates)
                        connections[i].add(new_neighbor)

    # Convert to agent network format
    return [{"agent_id": f"agent-{i}", "connections": [f"agent-{c}" for c in sorted(conns)]}
            for i, conns in connections.items()]


def assign_network_to_agents(agents: list, network: list) -> list:
    """
    Assign small-world network connections to agent profiles.
    Updates each agent's social_network field in-place.
    """
    agent_map = {a["id"]: a for a in agents}
    for node in network:
        agent_id = node["agent_id"]
        if agent_id in agent_map:
            agent_map[agent_id]["social_network"] = {
                "connections": node["connections"],
                "network_type": "small_world",
            }
    return agents


def build_agent_network(agents: list) -> list:
    """
    One-shot: build small-world network and assign to agents.
    beta=0.1 is the optimal value from UChicago research.
    """
    n = len(agents)
    k = min(6, max(2, n // 5))  # Each agent connects to ~6 neighbors
    network = watts_strogatz_network(n, k, beta=0.1)
    return assign_network_to_agents(agents, network)


# Stats for verification
def network_stats(agents: list) -> dict:
    """Compute network statistics for verification."""
    n = len(agents)
    edges = sum(len(a.get("social_network", {}).get("connections", [])) for a in agents) / 2
    avg_degree = edges * 2 / n if n > 0 else 0
    return {"agents": n, "total_edges": int(edges), "avg_degree": round(avg_degree, 1), "type": "small_world"}
