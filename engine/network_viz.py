"""
Agent Network Visualization — pyvis interactive graphs.
Three graph types: social network, product-buyer bipartite, emotion playback.
"""

from pyvis.network import Network

TYPE_COLORS = {
    "consumer": "#00d4ff",
    "smb": "#00ff88",
    "enterprise": "#ff6b6b",
    "competitor": "#ffaa00",
    "environment": "#aa88ff",
}
EMOTION_COLORS = {
    "excited": "#00ff88", "satisfied": "#88ff44", "curious": "#ffdd44",
    "neutral": "#888888", "indifferent": "#aa8866",
    "skeptical": "#ff8844", "frustrated": "#ff4444",
}


def build_agent_graph_html(agents: list, height: str = "650px",
                           title: str = "Agent Social Network") -> str:
    """Build interactive small-world agent network graph."""
    net = Network(height=height, width="100%", bgcolor="#1a1a2e",
                  font_color="white", directed=False)
    net.heading = title

    for agent in agents:
        atype = agent.get("type", "unknown")
        color = TYPE_COLORS.get(atype, "#888888")
        name = agent.get("name", agent.get("id", "?"))[:15]
        influence = agent.get("influence_weight", 1.0)
        budget = agent.get("budget_monthly_cny", "?")
        bdi = agent.get("bdi", {})
        beliefs = ", ".join(bdi.get("beliefs", [])[:2])

        tooltip = f"<b>{name}</b><br>Type: {atype}<br>Budget: {budget}<br>Beliefs: {beliefs}"
        net.add_node(agent["id"], label=name, color=color, title=tooltip,
                     size=max(8, influence * 12))

    seen = set()
    for agent in agents:
        for conn in agent.get("social_network", {}).get("connections", []):
            edge = tuple(sorted([agent["id"], conn]))
            if edge not in seen:
                seen.add(edge)
                net.add_edge(edge[0], edge[1], color="#333366", width=0.5)

    net.set_options("""
    { "physics": { "forceAtlas2Based": { "gravitationalConstant": -50, "springLength": 100, "springConstant": 0.08 }, "stabilization": { "iterations": 100 } },
      "interaction": { "hover": true, "tooltipDelay": 100, "navigationButtons": true } }
    """)
    return net.generate_html()


def build_bipartite_graph_html(products: list, agent_states: dict, agents: list,
                                height: str = "650px") -> str:
    """Build product-buyer bipartite graph."""
    net = Network(height=height, width="100%", bgcolor="#1a1a2e",
                  font_color="white", directed=False)

    # Product nodes
    for p in products:
        pid = p.get("product_id", p.get("id", "?"))
        name = p.get("product_name", p.get("name", "?"))[:20]
        status = p.get("status", "dead")
        color = "#00ff88" if status == "alive" else ("#ffaa00" if status == "struggling" else "#ff4444")
        buyers = p.get("purchasers", 0)
        net.add_node(f"prod-{pid}", label=name, color=color, shape="star",
                     title=f"{name}<br>Buyers: {buyers}<br>Status: {status}", size=25)

    # Agent nodes (buyers only)
    for aid, state in agent_states.items():
        purchased = state.get("purchased_products", {})
        if not purchased:
            continue
        profile = state.get("profile", {})
        name = profile.get("name", aid)[:12]
        atype = profile.get("type", "consumer")
        color = TYPE_COLORS.get(atype, "#888888")
        net.add_node(f"agent-{aid}", label=name, color=color,
                     title=f"{name} ({atype})", size=10)

    # Edges: agent → product (weight = price paid)
    for aid, state in agent_states.items():
        for pid, info in state.get("purchased_products", {}).items():
            price = info.get("price_paid", 0)
            net.add_edge(f"agent-{aid}", f"prod-{pid}",
                        value=max(1, price / 10), title=f"Paid: {price}")

    net.set_options("""
    { "physics": { "barnesHut": { "gravitationalConstant": -2000, "springLength": 200 }, "stabilization": { "iterations": 100 } },
      "interaction": { "hover": true, "navigationButtons": true } }
    """)
    return net.generate_html()


def build_emotion_timeline_html(agent_states: dict, agents: list,
                                 highlight_round: int = None) -> str:
    """Build emotion snapshot graph for a specific round."""
    net = Network(height="650px", width="100%", bgcolor="#1a1a2e",
                  font_color="white", directed=False)

    for agent in agents:
        aid = agent["id"]
        state = agent_states.get(aid, {})
        emotion = state.get("emotional_state", "neutral")
        color = EMOTION_COLORS.get(emotion, "#888888")
        name = agent.get("name", aid)[:12]

        # Show purchase status
        purchased = len(state.get("purchased_products", {}))
        border = "#00ff88" if purchased > 0 else "#444444"

        net.add_node(aid, label=name, color=color, title=f"{name}: {emotion} ({purchased} purchases)",
                     size=12, borderWidth=2, borderWidthSelected=4)

    # Small-world edges
    seen = set()
    for agent in agents:
        for conn in agent.get("social_network", {}).get("connections", []):
            edge = tuple(sorted([agent["id"], conn]))
            if edge not in seen:
                seen.add(edge)
                net.add_edge(edge[0], edge[1], color="#222244", width=0.3)

    net.set_options("""
    { "physics": { "forceAtlas2Based": { "gravitationalConstant": -30, "springLength": 80, "springConstant": 0.05 }, "stabilization": { "iterations": 80 } },
      "interaction": { "hover": true, "tooltipDelay": 50 } }
    """)
    return net.generate_html()
