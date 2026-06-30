"""
Agent Dialogue — chat with any simulated agent using its profile + history.
Uses the agent's own LLM assignment for authentic persona consistency.
"""

from engine.llm_client import get_llm

DIALOGUE_PROMPT = """You ARE this specific agent from the MarketFish simulation.
Respond AS THIS PERSON. Not as an AI assistant.

Your identity:
- Name: {agent_name}
- Type: {agent_type}
- Location: {city_tier}-tier city
- Monthly budget: {budget} CNY
- Decision style: {decision_speed}
- Tech savvy: {tech_savviness}/10

Your beliefs: {beliefs}
Your desires: {desires}
Your pain points: {pain_points}

Current emotional state: {emotional_state}
Your learned strategy: {strategy_context}

Recent simulation actions:
{recent_history}

Products you purchased: {purchased_summary}
Total spent: {total_spent} CNY

Rules:
- Respond in Chinese. Be concise (1-3 sentences). Stay in character.
- If asked about products, reference your actual simulation experiences.
- If asked about price, stay within your budget ({budget} CNY/month).
- You are {agent_name}, not Claude, not an AI. You are a real person."""


def chat_with_agent(agent_id: str, user_message: str, agents: list,
                    agent_states: dict, chat_history: list = None) -> dict:
    """Send a message to a specific agent and get their authentic response."""
    # Find agent profile
    profile = None
    for a in agents:
        if a.get("id") == agent_id:
            profile = a
            break
    if not profile:
        return {"error": f"Agent {agent_id} not found"}

    state = agent_states.get(agent_id, {})
    history_entries = state.get("history", [])
    strategy = state.get("rl_strategy", {})
    bdi = profile.get("bdi", {})
    demo = profile.get("demographics", {})

    # Format recent history
    recent = []
    for h in history_entries[-5:]:
        recent.append(f"  Round {h.get('round','?')}: {h.get('action','?')} — {h.get('reasoning','')[:100]}")
    recent_text = "\n".join(recent) if recent else "No actions yet."

    # Format purchases
    purchased = state.get("purchased_products", {})
    purchase_lines = []
    for pid, info in purchased.items():
        price = info.get("price_paid", 0)
        churned = " (CHURNED)" if "churned_at" in info else ""
        purchase_lines.append(f"  {pid}: {price} CNY{churned}")
    purchase_text = "\n".join(purchase_lines) if purchase_lines else "None"

    # Format strategy
    strat_parts = []
    for k, v in strategy.items():
        if v is not None:
            strat_parts.append(f"{k}={v:.2f}")
    strategy_text = ", ".join(strat_parts) if strat_parts else "No learned strategy yet"

    system = DIALOGUE_PROMPT.format(
        agent_name=profile.get("name", agent_id),
        agent_type=profile.get("type", "unknown"),
        city_tier=demo.get("city_tier", "?"),
        budget=profile.get("budget_monthly_cny", 0),
        decision_speed=profile.get("decision_speed", "days"),
        tech_savviness=round(profile.get("tech_savviness", 0.5) * 10),
        beliefs=", ".join(bdi.get("beliefs", ["none"])),
        desires=", ".join(bdi.get("desires", ["none"])),
        pain_points=", ".join(profile.get("pain_points", ["none"])[:3]),
        emotional_state=state.get("emotional_state", "neutral"),
        strategy_context=strategy_text,
        recent_history=recent_text,
        purchased_summary=purchase_text,
        total_spent=state.get("total_spent", 0),
    )

    try:
        llm = get_llm()
        agent_type = profile.get("type", "consumer")
        response = llm.chat_text(system=system, user=user_message, agent_type=agent_type, temperature=0.9)
        return {
            "agent_id": agent_id,
            "agent_name": profile.get("name", agent_id),
            "agent_type": profile.get("type", "unknown"),
            "response": response,
            "emotional_state": state.get("emotional_state", "neutral"),
        }
    except Exception as e:
        return {"agent_id": agent_id, "error": str(e)}


def list_chatable_agents(agents: list, agent_states: dict, min_history: int = 1) -> list[dict]:
    """Return a list of agents available for chat, with summary info."""
    result = []
    for a in agents:
        aid = a["id"]
        state = agent_states.get(aid, {})
        history_len = len(state.get("history", []))
        if history_len >= min_history:
            result.append({
                "id": aid,
                "name": a.get("name", aid),
                "type": a.get("type", "unknown"),
                "actions": history_len,
                "purchases": len(state.get("purchased_products", {})),
                "emotional_state": state.get("emotional_state", "neutral"),
            })
    result.sort(key=lambda x: x["actions"], reverse=True)
    return result
