"""
Agent Persistence Store — v6 Step 1.

Agents are assets, not consumables. After each simulation, agent profiles + states
+ RL strategies are persisted to disk. Subsequent runs load from store instead of
regenerating from scratch via LLM.

Storage: data_lake/gold/agents/agent-{id}.json + agent_index.json
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_store_root() -> Path:
    return Path(__file__).parent.parent / "data_lake" / "gold" / "agents"


class AgentStore:
    """CRUD for persisted agents. Thread-safe for reads, caller serializes writes."""

    def __init__(self, store_root: str = None):
        self.root = Path(store_root) if store_root else _default_store_root()
        self.root.mkdir(parents=True, exist_ok=True)

    # ── path helpers ──────────────────────────────────────────────
    def _agent_path(self, agent_id: str) -> Path:
        safe = agent_id.replace("/", "_").replace("\\", "_")
        return self.root / f"agent-{safe}.json"

    @property
    def index_path(self) -> Path:
        return self.root / "agent_index.json"

    # ── CRUD ──────────────────────────────────────────────────────
    def save(self, agent_id: str, profile: dict, state: dict = None,
             rl_strategy: dict = None, task_id: str = None) -> bool:
        """Persist one agent. Merges with existing record if present."""
        existing = self.load(agent_id) if self.exists(agent_id) else {}
        record = {
            "agent_id": agent_id,
            "profile": profile,
            "state": state or {},
            "rl_strategy": rl_strategy,
            "created_at": existing.get("created_at", _now()),
            "updated_at": _now(),
            "task_count": existing.get("task_count", 0) + (1 if task_id else 0),
            "task_ids": list(set(existing.get("task_ids", []) + ([task_id] if task_id else []))),
        }
        # Convert sets in state to lists for JSON
        if record["state"]:
            record["state"] = _serialize_state(record["state"])
        try:
            self._agent_path(agent_id).write_text(
                json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            return False

    def load(self, agent_id: str) -> Optional[dict]:
        """Load one agent record. Returns None if not found."""
        p = self._agent_path(agent_id)
        if not p.exists():
            return None
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
            # Restore sets
            if record.get("state"):
                record["state"] = _deserialize_state(record["state"])
            return record
        except Exception:
            return None

    def load_all(self) -> list[dict]:
        """Load all agents. Returns list of records (may be empty)."""
        records = []
        for p in sorted(self.root.glob("agent-*.json")):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
                if r.get("state"):
                    r["state"] = _deserialize_state(r["state"])
                records.append(r)
            except Exception:
                pass
        return records

    def exists(self, agent_id: str) -> bool:
        return self._agent_path(agent_id).exists()

    def count(self) -> int:
        return len(list(self.root.glob("agent-*.json")))

    def delete(self, agent_id: str) -> bool:
        p = self._agent_path(agent_id)
        if p.exists():
            p.unlink()
            return True
        return False

    # ── batch ─────────────────────────────────────────────────────
    def save_batch(self, agent_states: dict, task_id: str = None) -> int:
        """Save all agents from a simulation run. Returns count saved.

        agent_states: {agent_id: {profile, history, purchased_products, ...}}
        """
        saved = 0
        for agent_id, state in agent_states.items():
            profile = state.get("profile", {})
            rl = state.get("rl_strategy")
            if self.save(agent_id, profile, state, rl, task_id):
                saved += 1
        self._rebuild_index()
        return saved

    # ── index ─────────────────────────────────────────────────────
    def _rebuild_index(self) -> dict:
        """Rebuild in-memory index from disk. Returns index dict."""
        index = {"total": 0, "by_type": {}, "by_decision_speed": {}, "agent_ids": []}
        for record in self.load_all():
            index["total"] += 1
            index["agent_ids"].append(record["agent_id"])
            t = record["profile"].get("type", "unknown")
            index["by_type"][t] = index["by_type"].get(t, 0) + 1
            ds = record["profile"].get("decision_speed", "unknown")
            index["by_decision_speed"][ds] = index["by_decision_speed"].get(ds, 0) + 1

        self.index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        return index

    def get_index(self) -> dict:
        """Return current index, rebuilding if missing."""
        if not self.index_path.exists():
            return self._rebuild_index()
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return self._rebuild_index()

    # ── sampling ──────────────────────────────────────────────────
    def sample(self, target_count: int, strategy: str = "stratified",
               task_context: dict = None) -> list[dict]:
        """Sample agents from the pool.

        Args:
            target_count: how many agents to select
            strategy: 'random' | 'stratified' | 'experienced'
            task_context: optional context for relevance-based sampling

        Returns list of agent records (profile+state ready for simulation).
        """
        all_records = self.load_all()
        pool_size = len(all_records)
        if pool_size == 0:
            return []
        if pool_size <= target_count:
            return all_records

        if strategy == "random":
            import random
            return random.sample(all_records, target_count)

        if strategy == "stratified":
            # Group by type, sample proportionally
            by_type = {}
            for r in all_records:
                t = r["profile"].get("type", "unknown")
                by_type.setdefault(t, []).append(r)

            import random
            selected = []
            for t, agents in by_type.items():
                n = max(1, round(target_count * len(agents) / pool_size))
                n = min(n, len(agents))
                selected.extend(random.sample(agents, n))

            # Trim or pad to exact target
            if len(selected) > target_count:
                selected = random.sample(selected, target_count)
            elif len(selected) < target_count:
                remaining = [r for r in all_records if r not in selected]
                extra = random.sample(remaining, min(target_count - len(selected), len(remaining)))
                selected.extend(extra)
            return selected

        if strategy == "experienced":
            # Prefer agents with more tasks completed
            sorted_records = sorted(all_records, key=lambda r: r.get("task_count", 0), reverse=True)
            return sorted_records[:target_count]

        # Default: random
        import random
        return random.sample(all_records, target_count)

    def stats(self) -> dict:
        """Human-readable pool statistics."""
        index = self.get_index()
        records = self.load_all()
        task_counts = [r.get("task_count", 0) for r in records]
        avg_tasks = round(sum(task_counts) / max(len(task_counts), 1), 1)
        max_tasks = max(task_counts) if task_counts else 0
        return {
            "total_agents": self.count(),
            "by_type": index.get("by_type", {}),
            "avg_tasks_per_agent": avg_tasks,
            "max_tasks": max_tasks,
            "oldest_agent": min((r.get("created_at", "") for r in records), default=""),
            "newest_agent": max((r.get("updated_at", "") for r in records), default=""),
        }


# ── serialization helpers ──────────────────────────────────────
def _serialize_state(state: dict) -> dict:
    """Convert sets and non-serializable objects to JSON-safe types."""
    out = {}
    for k, v in state.items():
        if isinstance(v, set):
            out[k] = list(v)
        elif isinstance(v, dict):
            out[k] = {str(dk): dv for dk, dv in v.items()}
        elif k == "profile":
            out[k] = v  # already a dict, keep as-is
        else:
            out[k] = v
    return out


def _deserialize_state(state: dict) -> dict:
    """Restore lists back to sets where appropriate."""
    out = {}
    set_keys = {"discovered_products"}
    for k, v in state.items():
        if k in set_keys and isinstance(v, list):
            out[k] = set(v)
        else:
            out[k] = v
    return out
