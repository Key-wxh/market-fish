"""
Agent Runtime — L0 Lifecycle Engine

Agent lifecycle management (create/start/pause/resume/terminate),
task queue, and threaded execution runner.

Pilot: 10 agents with persistent state, running independently.
This is the foundation for scaling from batch LLM calls to true Agent autonomy.

Design: simple threading pool + file-based state via AgentStore.
Celery/Redis not needed for pilot (<100 agents).
"""
import json, time, uuid, threading
from pathlib import Path
from datetime import datetime, timezone
from queue import Queue, Empty
from typing import Optional
from engine.agent_store import AgentStore


# ── Lifecycle States ──
class Lifecycle:
    CREATED = "created"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"

    VALID_TRANSITIONS = {
        CREATED: {IDLE, RUNNING, TERMINATED},
        IDLE: {RUNNING, PAUSED, TERMINATED},
        RUNNING: {IDLE, PAUSED, COMPLETED, FAILED, TERMINATED},
        PAUSED: {IDLE, RUNNING, TERMINATED},
        COMPLETED: {IDLE, TERMINATED},
        FAILED: {IDLE, TERMINATED},
        TERMINATED: set(),
    }

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        return to_state in cls.VALID_TRANSITIONS.get(from_state, set())


# ── Task ──
class AgentTask:
    """A unit of work assigned to an agent."""
    def __init__(self, task_type: str, input_data: dict = None,
                 agent_id: str = None, task_id: str = None):
        self.task_id = task_id or f"task-{uuid.uuid4().hex[:8]}"
        self.agent_id = agent_id
        self.type = task_type  # learn, analyze, debate, report, custom
        self.input = input_data or {}
        self.output = None
        self.status = "pending"  # pending → running → completed/failed
        self.error = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.started_at = None
        self.completed_at = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "agent_id": self.agent_id,
            "type": self.type, "input": self.input, "output": self.output,
            "status": self.status, "error": self.error,
            "created_at": self.created_at, "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentTask":
        t = cls(d.get("type"), d.get("input"), d.get("agent_id"), d.get("task_id"))
        t.output = d.get("output")
        t.status = d.get("status", "pending")
        t.error = d.get("error")
        t.created_at = d.get("created_at")
        t.started_at = d.get("started_at")
        t.completed_at = d.get("completed_at")
        return t


# ── Task Runner (caller provides the execution logic) ──
TaskHandler = callable  # def handler(agent_record: dict, task: AgentTask) -> dict


# ── Agent Runtime ──
class AgentRuntime:
    """
    Manages agent lifecycle + task execution.

    Usage:
        rt = AgentRuntime()
        rt.create_agent(profile)
        rt.start(agent_id)
        rt.assign_task(agent_id, AgentTask("analyze", {...}))
        rt.run_all()  # blocking
    """

    
    # ── Quality Scoring (ruflo Agent Quality Tracker) ──

    def score_agent(self, agent_id: str, success: bool, latency_ms: float = 0):
        """Track agent quality: success rate + latency over time."""
        agent = self.load(agent_id)
        if not agent:
            return
        q = agent.get("quality", {"successes": 0, "failures": 0, "avg_latency_ms": 0, "total_calls": 0})
        q["total_calls"] = q.get("total_calls", 0) + 1
        if success:
            q["successes"] = q.get("successes", 0) + 1
        else:
            q["failures"] = q.get("failures", 0) + 1
        if latency_ms > 0:
            old_avg = q.get("avg_latency_ms", 0)
            n = q["total_calls"]
            q["avg_latency_ms"] = (old_avg * (n - 1) + latency_ms) / n
        q["score"] = round(q["successes"] / max(q["total_calls"], 1), 2)
        agent["quality"] = q
        self.save(agent_id, agent)
        return q

    def get_agent_quality(self, agent_id: str) -> dict:
        """Get agent quality score. Returns {score, successes, failures, total_calls, status}."""
        agent = self.load(agent_id)
        q = agent.get("quality", {}) if agent else {}
        score = q.get("score", 0.5)
        status = "healthy" if score >= 0.7 else "degraded" if score >= 0.4 else "failed"
        return {"score": score, "status": status,
                "successes": q.get("successes", 0), "failures": q.get("failures", 0),
                "total_calls": q.get("total_calls", 0)}

    # ── Circuit Breaker (ruflo: auto-downgrade failing agents) ──

    def check_circuit(self, agent_id: str) -> bool:
        """Returns True if agent is allowed to run, False if circuit is open."""
        agent = self.load(agent_id)
        if not agent:
            return True
        cb = agent.get("circuit_breaker", {"consecutive_failures": 0, "open": False, "opened_at": None})
        if cb.get("open"):
            # Auto-reset after 1 hour
            opened = cb.get("opened_at")
            if opened:
                try:
                    from datetime import datetime, timezone
                    age = (datetime.now(timezone.utc) -
                           datetime.fromisoformat(opened.replace("Z", "+00:00"))).total_seconds()
                    if age > 3600:
                        cb["open"] = False
                        cb["consecutive_failures"] = 0
                        cb["opened_at"] = None
                        agent["circuit_breaker"] = cb
                        self.save(agent_id, agent)
                        return True
                except Exception:
                    pass
            return False
        return True

    def record_failure(self, agent_id: str):
        """Record a failure. After 3 consecutive, open circuit breaker."""
        agent = self.load(agent_id)
        if not agent:
            return
        cb = agent.get("circuit_breaker", {"consecutive_failures": 0, "open": False, "opened_at": None})
        cb["consecutive_failures"] = cb.get("consecutive_failures", 0) + 1
        if cb["consecutive_failures"] >= 3:
            cb["open"] = True
            from datetime import datetime, timezone
            cb["opened_at"] = datetime.now(timezone.utc).isoformat()
            print(f"  [CIRCUIT-BREAKER] Agent {agent_id} tripped: {cb['consecutive_failures']} consecutive failures")
        agent["circuit_breaker"] = cb
        self.save(agent_id, agent)

    def record_success(self, agent_id: str):
        """Reset failure counter on success."""
        agent = self.load(agent_id)
        if not agent:
            return
        cb = agent.get("circuit_breaker", {"consecutive_failures": 0, "open": False, "opened_at": None})
        cb["consecutive_failures"] = 0
        cb["open"] = False
        cb["opened_at"] = None
        agent["circuit_breaker"] = cb


    def __init__(self, store_root: str = None, max_workers: int = 4):
        self.store = AgentStore(store_root)
        self.task_queue = Queue()
        self.max_workers = max_workers
        self._workers = []
        self._handler: TaskHandler = None
        self._running = False
        self._lock = threading.Lock()

    # ── Lifecycle ──

    def create_agent(self, profile: dict, state: dict = None) -> str:
        """Create a new agent with lifecycle state."""
        agent_id = profile.get("id") or f"agent-{uuid.uuid4().hex[:12]}"
        profile["id"] = agent_id
        state = state or {}
        state["lifecycle"] = Lifecycle.CREATED
        state["task_history"] = state.get("task_history", [])
        state["memory"] = state.get("memory", {})  # L1-lite: key-value store
        self.store.save(agent_id, profile, state)
        return agent_id

    def get_lifecycle(self, agent_id: str) -> str:
        record = self.store.load(agent_id)
        if not record:
            return Lifecycle.TERMINATED
        return record.get("state", {}).get("lifecycle", Lifecycle.CREATED)

    def transition(self, agent_id: str, to_state: str) -> bool:
        """Attempt a lifecycle state transition."""
        current = self.get_lifecycle(agent_id)
        if not Lifecycle.can_transition(current, to_state):
            return False
        with self._lock:
            record = self.store.load(agent_id)
            if not record:
                return False
            record["state"]["lifecycle"] = to_state
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.store.save(agent_id, record["profile"], record["state"])
            return True

    def start(self, agent_id: str) -> bool:
        return self.transition(agent_id, Lifecycle.RUNNING)

    def pause(self, agent_id: str) -> bool:
        return self.transition(agent_id, Lifecycle.PAUSED)

    def resume(self, agent_id: str) -> bool:
        return self.transition(agent_id, Lifecycle.RUNNING)

    def complete(self, agent_id: str) -> bool:
        return self.transition(agent_id, Lifecycle.COMPLETED)

    def fail(self, agent_id: str, error: str = "") -> bool:
        record = self.store.load(agent_id)
        if record:
            record["state"]["last_error"] = error
            self.store.save(agent_id, record["profile"], record["state"])
        return self.transition(agent_id, Lifecycle.FAILED)

    def terminate(self, agent_id: str) -> bool:
        return self.transition(agent_id, Lifecycle.TERMINATED)

    # ── Memory (L1-lite) ──

    def remember(self, agent_id: str, key: str, value) -> bool:
        """Store a memory entry for an agent."""
        record = self.store.load(agent_id)
        if not record:
            return False
        memory = record["state"].setdefault("memory", {})
        memory[key] = {
            "value": value,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        self.store.save(agent_id, record["profile"], record["state"])
        return True

    def recall(self, agent_id: str, key: str, default=None):
        """Recall a memory entry."""
        record = self.store.load(agent_id)
        if not record:
            return default
        mem = record["state"].get("memory", {}).get(key, {})
        return mem.get("value", default)

    # ── Tasks ──

    def assign_task(self, agent_id: str, task: AgentTask) -> str:
        """Assign a task to an agent and enqueue it."""
        task.agent_id = agent_id
        task.status = "pending"

        # Store task in agent's task history
        record = self.store.load(agent_id)
        if record:
            history = record["state"].setdefault("task_history", [])
            history.append(task.to_dict())
            # Keep last 100 tasks
            if len(history) > 100:
                history = history[-100:]
            record["state"]["task_history"] = history
            self.store.save(agent_id, record["profile"], record["state"])

        self.task_queue.put((agent_id, task))
        return task.task_id

    # ── Execution ──

    def set_handler(self, handler: TaskHandler):
        """Set the function that executes tasks."""
        self._handler = handler

    def _worker_loop(self):
        """Worker thread: dequeue and execute tasks."""
        while self._running:
            try:
                agent_id, task = self.task_queue.get(timeout=1)
            except Empty:
                continue

            try:
                # Transition to RUNNING
                self.transition(agent_id, Lifecycle.RUNNING)
                task.status = "running"
                task.started_at = datetime.now(timezone.utc).isoformat()

                # Load agent record
                record = self.store.load(agent_id)

                # Execute
                if self._handler:
                    result = self._handler(record, task)
                    task.output = result
                    task.status = "completed"
                    self.complete(agent_id)
                else:
                    task.status = "completed"
                    task.output = {"note": "no handler set — task skipped"}
                    self.transition(agent_id, Lifecycle.IDLE)

            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                self.fail(agent_id, str(e))

            finally:
                task.completed_at = datetime.now(timezone.utc).isoformat()
                self.task_queue.task_done()

    def start_workers(self, handler: TaskHandler = None):
        """Start worker threads."""
        if handler:
            self._handler = handler
        self._running = True
        self._workers = []
        for i in range(self.max_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"agent-wkr-{i}")
            t.start()
            self._workers.append(t)

    def stop_workers(self):
        """Stop worker threads gracefully."""
        self._running = False
        for t in self._workers:
            t.join(timeout=5)

    def run_all(self, handler: TaskHandler = None):
        """Blocking: process all queued tasks. For pilot/single-run use."""
        self.start_workers(handler)
        self.task_queue.join()  # Block until all done
        self.stop_workers()

    def queue_size(self) -> int:
        return self.task_queue.qsize()

    # ── Stats ──

    def stats(self) -> dict:
        """Runtime statistics."""
        agents = self.store.load_all()
        statuses = {}
        for a in agents:
            lc = a.get("state", {}).get("lifecycle", "unknown")
            statuses[lc] = statuses.get(lc, 0) + 1
        return {
            "total_agents": len(agents),
            "by_lifecycle": statuses,
            "queue_size": self.task_queue.qsize(),
            "workers": len(self._workers),
            "running": self._running,
        }


# ── Pilot: 10-agent bootstrap ──

def create_pilot_agents(runtime: AgentRuntime, count: int = 10) -> list[str]:
    """Create N pilot agents with diverse profiles. Returns list of agent_ids."""
    profiles = _pilot_profiles()[:count]
    ids = []
    for p in profiles:
        aid = runtime.create_agent(p, state={
            "lifecycle": Lifecycle.CREATED,
            "memory": {"bootstrapped": True, "created_by": "pilot"},
        })
        runtime.transition(aid, Lifecycle.IDLE)
        ids.append(aid)
    return ids


def _pilot_profiles() -> list[dict]:
    """Generate diverse pilot agent profiles."""
    return [
        {"id": "pilot-macro-analyst", "type": "analyst", "name": "宏观分析师",
         "occupation": "宏观经济研究员", "expertise": ["gdp", "inflation", "monetary_policy"],
         "decision_speed": "weeks", "tech_savviness": 0.6, "budget_monthly_cny": 50000},
        {"id": "pilot-tech-scout", "type": "analyst", "name": "技术侦察员",
         "occupation": "科技行业分析师", "expertise": ["ai", "semiconductor", "software"],
         "decision_speed": "days", "tech_savviness": 0.95, "budget_monthly_cny": 30000},
        {"id": "pilot-retail-trader", "type": "consumer", "name": "散户老王",
         "occupation": "个体投资者", "expertise": ["a_shares", "technical_analysis"],
         "decision_speed": "impulse", "tech_savviness": 0.4, "budget_monthly_cny": 5000},
        {"id": "pilot-supply-chain", "type": "analyst", "name": "供应链专家",
         "occupation": "产业链研究员", "expertise": ["copper", "lithium", "semiconductor_equipment"],
         "decision_speed": "weeks", "tech_savviness": 0.5, "budget_monthly_cny": 40000},
        {"id": "pilot-sentiment-tracker", "type": "analyst", "name": "情绪追踪员",
         "occupation": "社交媒体分析师", "expertise": ["weibo", "baidu_trends", "sentiment"],
         "decision_speed": "days", "tech_savviness": 0.8, "budget_monthly_cny": 20000},
        {"id": "pilot-risk-manager", "type": "analyst", "name": "风控官",
         "occupation": "风险管理师", "expertise": ["tail_risk", "black_swan", "portfolio"],
         "decision_speed": "weeks", "tech_savviness": 0.7, "budget_monthly_cny": 60000},
        {"id": "pilot-consumer-watch", "type": "consumer", "name": "消费观察员",
         "occupation": "消费行业分析师", "expertise": ["retail", "ecommerce", "consumer_confidence"],
         "decision_speed": "days", "tech_savviness": 0.6, "budget_monthly_cny": 25000},
        {"id": "pilot-policy-decoder", "type": "analyst", "name": "政策解读者",
         "occupation": "政策研究员", "expertise": ["fiscal_policy", "regulation", "industrial_policy"],
         "decision_speed": "weeks", "tech_savviness": 0.5, "budget_monthly_cny": 35000},
        {"id": "pilot-global-scout", "type": "analyst", "name": "全球侦察兵",
         "occupation": "国际宏观分析师", "expertise": ["global_gdp", "fed", "geopolitics"],
         "decision_speed": "weeks", "tech_savviness": 0.7, "budget_monthly_cny": 45000},
        {"id": "pilot-debate-moderator", "type": "analyst", "name": "辩论主持人",
         "occupation": "研究协调员", "expertise": ["consensus", "debate", "meta_analysis"],
         "decision_speed": "days", "tech_savviness": 0.85, "budget_monthly_cny": 30000},
    ]
