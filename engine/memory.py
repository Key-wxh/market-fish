"""
Memory Module — v6 Step 3.

Generative Agents (Park et al., UIST 2023, arxiv 2304.03442):
  Memory stream + retrieval (importance/recency/relevance) + reflection + consolidation.

Each agent maintains a memory stream. Before decisions, relevant memories are retrieved
and injected into the decision prompt. After decisions, new memories are stored.
Periodic reflection generates high-level insights.
"""
import json
import time
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_epoch() -> float:
    return time.time()


def _default_store_root() -> Path:
    return Path(__file__).parent.parent / "data_lake" / "gold" / "memories"


class MemoryStream:
    """Per-agent memory stream with retrieval, reflection, and consolidation."""

    def __init__(self, agent_id: str, store_root: str = None,
                 capacity: int = 1000, reflection_interval: int = 10,
                 recency_weight: float = 0.6, relevance_weight: float = 0.3,
                 importance_weight: float = 0.1, reflection_top_k: int = 3):
        self.agent_id = agent_id
        self.root = Path(store_root) if store_root else _default_store_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.capacity = capacity
        self.reflection_interval = reflection_interval
        self.recency_weight = recency_weight
        self.relevance_weight = relevance_weight
        self.importance_weight = importance_weight
        self.reflection_top_k = reflection_top_k
        self._memories: list[dict] = []
        self._loaded = False

    # ── persistence ──────────────────────────────────────────────
    @property
    def _path(self) -> Path:
        safe = self.agent_id.replace("/", "_").replace("\\", "_")
        return self.root / f"mem-{safe}.json"

    def _load(self):
        if self._loaded:
            return
        if self._path.exists():
            try:
                self._memories = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._memories = []
        else:
            self._memories = []
        self._loaded = True

    def _save(self):
        self._path.write_text(
            json.dumps(self._memories, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── core operations ──────────────────────────────────────────
    def add(self, content: str, round_num: int = 0, task_id: str = "",
            mem_type: str = "observation", importance: float = None) -> dict:
        """Add a memory. If importance is None, estimate from content heuristics."""
        self._load()
        if importance is None:
            importance = self._estimate_importance(content)
        mem = {
            "id": f"mem-{len(self._memories):05d}",
            "agent_id": self.agent_id,
            "content": content,
            "importance": round(min(1.0, max(0.0, importance)), 2),
            "type": mem_type,
            "round": round_num,
            "task_id": task_id,
            "timestamp": _now(),
            "epoch": _now_epoch(),
        }
        self._memories.append(mem)
        self._save()
        return mem

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve top-K memories by combined score (recency + relevance + importance)."""
        self._load()
        if not self._memories:
            return []

        now = _now_epoch()
        scored = []
        for mem in self._memories:
            hours = (now - mem.get("epoch", now)) / 3600.0
            # Recency: exponential decay, half-life ~12 hours
            recency = math.exp(-0.058 * hours)
            # Relevance: simple keyword overlap scoring
            relevance = self._keyword_score(mem.get("content", ""), query)
            # Importance: stored tag
            importance = mem.get("importance", 0.5)
            # Combined score
            score = (self.recency_weight * recency +
                     self.relevance_weight * relevance +
                     self.importance_weight * importance)
            scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in scored[:top_k]]

    def reflect(self, llm_client=None) -> list[dict]:
        """Generate high-level insights from top memories. Requires an LLM client.

        If no LLM client provided, generates a simple heuristic reflection.
        Returns list of new reflection memories.
        """
        self._load()
        if len(self._memories) < self.reflection_top_k:
            return []

        # Take top-K highest-importance memories
        top = sorted(self._memories, key=lambda m: m.get("importance", 0), reverse=True)
        top = top[:self.reflection_top_k * 3]  # Wider pool for LLM

        if llm_client:
            return self._llm_reflect(llm_client, top)
        else:
            return self._heuristic_reflect(top)

    def consolidate(self, max_capacity: int = None) -> int:
        """Remove lowest-scored memories if over capacity. Returns number removed."""
        self._load()
        cap = max_capacity or self.capacity
        if len(self._memories) <= cap:
            return 0

        # Score all memories
        now = _now_epoch()
        scored = []
        for mem in self._memories:
            hours = (now - mem.get("epoch", now)) / 3600.0
            recency = math.exp(-0.058 * hours)
            importance = mem.get("importance", 0.5)
            scored.append((recency * 0.3 + importance * 0.7, mem))

        scored.sort(key=lambda x: x[0])
        remove_count = len(self._memories) - cap
        self._memories = [mem for _, mem in scored[remove_count:]]
        self._save()
        return remove_count

    def stats(self) -> dict:
        """Memory statistics for this agent."""
        self._load()
        types = {}
        total_imp = 0.0
        for mem in self._memories:
            t = mem.get("type", "unknown")
            types[t] = types.get(t, 0) + 1
            total_imp += mem.get("importance", 0)
        return {
            "agent_id": self.agent_id,
            "total": len(self._memories),
            "by_type": types,
            "avg_importance": round(total_imp / max(len(self._memories), 1), 2),
            "reflection_count": types.get("reflection", 0),
        }

    # ── internal helpers ─────────────────────────────────────────
    def _estimate_importance(self, content: str) -> float:
        """Heuristic importance scoring based on content signals."""
        score = 0.3  # baseline
        signals = {
            "regret": 0.3, "后悔": 0.3, "recommend": 0.25, "推荐": 0.25,
            "purchase": 0.2, "buy": 0.2, "买": 0.2, "churn": 0.2, "流失": 0.2,
            "fomo": 0.15, "save": 0.1, "expensive": 0.1, "贵": 0.1,
            "discover": 0.05, "发现": 0.05, "ignore": -0.1, "skip": -0.1,
        }
        for keyword, boost in signals.items():
            if keyword.lower() in content.lower():
                score += boost
        return min(1.0, max(0.0, score))

    def _keyword_score(self, text: str, query: str) -> float:
        """Simple Jaccard-like keyword overlap score."""
        if not query or not text:
            return 0.0
        q_words = set(query.lower().split())
        t_words = set(text.lower().split())
        if not q_words:
            return 0.0
        overlap = len(q_words & t_words)
        return min(1.0, overlap / len(q_words))

    def _heuristic_reflect(self, top_memories: list[dict]) -> list[dict]:
        """Generate a simple heuristic reflection without LLM."""
        types = {}
        for m in top_memories:
            t = m.get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        content = f"Auto-reflection: {len(top_memories)} recent memories — "
        parts = [f"{t}:{c}" for t, c in sorted(types.items(), key=lambda x: x[1], reverse=True)[:3]]
        content += ", ".join(parts)
        mem = self.add(content=content, round_num=-1, task_id="reflection",
                       mem_type="reflection", importance=0.8)
        return [mem]

    def _llm_reflect(self, llm, top_memories: list[dict]) -> list[dict]:
        """Use LLM to generate reflective insights."""
        mem_text = "\n".join(
            f"- [{m.get('type','?')}] R{m.get('round','?')}: {m.get('content','')[:200]}"
            for m in top_memories[:15]
        )
        prompt = f"""You are an agent reflecting on your recent experiences to discover patterns.

Recent memories:
{mem_text}

Based on these memories, generate 3 high-level insights about your behavior, preferences, and decision patterns.
Output as JSON: {{"insights": ["insight 1", "insight 2", "insight 3"]}}
Each insight should be one sentence, written in first person (e.g., "I tend to...")."""
        try:
            result = llm.chat_json(system="You are a reflective AI agent.", user=prompt, temperature=0.5)
            insights = result.get("insights", [])
            new_mems = []
            for insight in insights[:5]:
                mem = self.add(content=insight, round_num=-1, task_id="reflection",
                               mem_type="reflection", importance=0.85)
                new_mems.append(mem)
            return new_mems
        except Exception:
            return self._heuristic_reflect(top_memories)


# ── batch helpers ──────────────────────────────────────────────
def inject_memories_to_context(agent_id: str, decision_context: str,
                               memory_streams: dict = None, top_k: int = 3) -> str:
    """Retrieve relevant memories and inject into agent decision context.

    Args:
        agent_id: the agent making a decision
        decision_context: the current product/market context
        memory_streams: {agent_id: MemoryStream} dict (created on demand if None)
        top_k: how many memories to retrieve

    Returns a string snippet to append to the decision prompt, or empty string.
    """
    if memory_streams and agent_id in memory_streams:
        ms = memory_streams[agent_id]
    else:
        ms = MemoryStream(agent_id)

    memories = ms.retrieve(query=decision_context, top_k=top_k)
    if not memories:
        return ""

    lines = ["\nYOUR PAST EXPERIENCES (from memory):"]
    for m in memories:
        t = m.get("type", "obs")
        lines.append(f"  [{t}] {m.get('content', '')[:150]}")
    return "\n".join(lines)


def record_decision_memory(agent_id: str, decision: dict, round_num: int,
                           task_id: str = "", memory_streams: dict = None):
    """Record an agent's decision as a memory.

    Args:
        agent_id: the agent who made the decision
        decision: the decision dict from simulator (action, reasoning, product_id, etc.)
        round_num: current simulation round
        task_id: current task identifier
        memory_streams: {agent_id: MemoryStream} dict
    """
    action = decision.get("action", "unknown")
    reasoning = decision.get("reasoning", "")
    product_id = decision.get("product_id", "")
    wtp = decision.get("willingness_to_pay_cny", 0)

    # Build a natural memory sentence
    mem_type = "observation"
    content_parts = []
    if action == "purchase":
        mem_type = "purchase"
        content_parts.append(f"Purchased {product_id} for ¥{wtp}")
    elif action == "churn":
        mem_type = "churn"
        content_parts.append(f"Stopped using {product_id}")
    elif action == "recommend":
        mem_type = "recommend"
        content_parts.append(f"Recommended {product_id} to others")
    elif action == "discover":
        mem_type = "discover"
        content_parts.append(f"Discovered {product_id}")
    if reasoning:
        content_parts.append(f"Reason: {reasoning[:200]}")
    if not content_parts:
        content_parts.append(f"Action: {action}")

    content = ". ".join(content_parts)

    if memory_streams and agent_id in memory_streams:
        ms = memory_streams[agent_id]
    else:
        ms = MemoryStream(agent_id)

    ms.add(content=content, round_num=round_num, task_id=task_id, mem_type=mem_type)
