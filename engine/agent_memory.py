"""
Agent Memory Engine — L1 Memory System (v2 with embeddings)

Three-tier memory model:
  Working (WM):  current session, high recency, fast decay
  Short-term (STM): recent sessions, moderate retention
  Long-term (LTM): important events, permanent storage, low decay

Storage: file-based JSON (DB-ready)
Retrieval: vector similarity (cosine) + time decay scoring, keyword fallback
"""
import json, time, re, os, math
from datetime import datetime, timezone, timedelta
from typing import Optional, List
try:
    from engine.auth import get_supabase
except ImportError:
    get_supabase = None

# ── Embedding Config ──
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
EMBEDDING_DIM = 1024  # DeepSeek embedding dimension
_embedding_cache: dict = {}  # Simple in-memory cache to avoid duplicate API calls


# ── Memory Tier Constants ──
WM_TTL_HOURS = 24        # Working memory: 24 hours
STM_TTL_DAYS = 7          # Short-term: 7 days
LTM_TTL_DAYS = 365 * 10   # Long-term: essentially permanent

# Importance thresholds
IMPORTANCE_LOW = 0.3      # Below this: likely to be forgotten
IMPORTANCE_MID = 0.5      # Above this: retained in STM
IMPORTANCE_HIGH = 0.8     # Above this: promoted to LTM

# Time decay: simplified Ebbinghaus curve
# Score = importance * e^(-age_hours / half_life_hours)
WM_HALF_LIFE = 6          # Working memory: half-life 6h
STM_HALF_LIFE = 72        # Short-term: half-life 3 days
LTM_HALF_LIFE = 8760      # Long-term: half-life 1 year

TABLE = "agent_memories"


# ── Schema ──
# Run this in Supabase SQL Editor to enable full DB-backed memory:
# (Without this, file-based JSON fallback is used automatically)
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.agent_memories (
    id BIGSERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'working',
    content TEXT NOT NULL,
    keywords TEXT[] DEFAULT '{}',
    embedding JSONB DEFAULT '[]'::jsonb,
    importance REAL DEFAULT 0.5,
    access_count INT DEFAULT 0,
    last_accessed TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_memories_agent ON agent_memories(agent_id, tier);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON agent_memories(agent_id, importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created ON agent_memories(agent_id, created_at DESC);
"""

# File-based fallback
import json as _json
from pathlib import Path as _Path

def _memory_file(agent_id: str) -> _Path:
    """File path for agent's memory JSON."""
    root = _Path(__file__).parent.parent / "data_lake" / "gold" / "memories"
    root.mkdir(parents=True, exist_ok=True)
    safe = agent_id.replace("/", "_").replace("\\", "_")
    return root / f"mem-{safe}.json"

def _load_memories(agent_id: str) -> list[dict]:
    """Load memories from JSON file."""
    f = _memory_file(agent_id)
    if f.exists():
        try:
            return _json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_memories(agent_id: str, memories: list[dict]):
    """Save memories to JSON file."""
    _memory_file(agent_id).write_text(_json.dumps(memories, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Embedding + Vector Similarity ──

def generate_embedding(text: str) -> List[float] | None:
    """
    Generate semantic embedding vector.
    Strategy: Try DeepSeek API → fallback to local TF-IDF-style vector.
    """
    cache_key = text[:200]
    if cache_key in _embedding_cache:
        return _embedding_cache[cache_key]

    # Try DeepSeek embeddings API
    if DEEPSEEK_KEY:
        try:
            import urllib.request
            body = json.dumps({
                "model": "deepseek-chat",
                "input": text[:4000],
            })
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/embeddings",
                data=body.encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                }
            )
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            emb = data.get("data", [{}])[0].get("embedding", [])
            if emb and len(emb) > 0:
                _embedding_cache[cache_key] = emb
                return emb
        except Exception:
            pass

    # Local fallback: unigram + bigram TF vector
    # Works for Chinese — unigrams catch shared characters, bigrams add context
    grams = {}
    text_clean = re.sub(r'[^一-鿿㐀-䶿\w]', '', text.lower())
    # Unigrams (single chars)
    for i in range(len(text_clean)):
        g = text_clean[i]
        grams[g] = grams.get(g, 0) + 1
    # Bigrams
    for i in range(len(text_clean) - 1):
        g = text_clean[i:i+2]
        grams[g] = grams.get(g, 0) + 2  # Bigrams weighted 2x
    # Store as sorted list of "term:count" strings
    vec = sorted(f"{k}:{v}" for k, v in grams.items())
    _embedding_cache[cache_key] = vec
    return vec


def cosine_similarity(a: List, b: List) -> float:
    """Compute similarity between two embedding vectors.
    For float vectors: cosine similarity.
    For string sets (bigrams): Jaccard similarity.
    """
    if not a or not b:
        return 0.0
    # Detect vector type
    if isinstance(a[0], str) or isinstance(b[0], str):
        # Weighted Jaccard on "term:count" strings
        def parse(s):
            d = {}
            for x in s:
                parts = x.rsplit(":", 1)
                if len(parts) == 2:
                    d[parts[0]] = int(parts[1])
            return d
        da, db = parse(a), parse(b)
        all_keys = set(da.keys()) | set(db.keys())
        if not all_keys:
            return 0.0
        intersection = sum(min(da.get(k, 0), db.get(k, 0)) for k in all_keys)
        union = sum(max(da.get(k, 0), db.get(k, 0)) for k in all_keys)
        return intersection / union if union > 0 else 0.0
    elif len(a) == len(b):
        # Cosine for float vectors
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    return 0.0


# ── Core Memory Engine ──

class MemoryEngine:
    """Per-agent memory with three-tier storage and time-decay retrieval.

    Primary: file-based JSON storage (always available).
    Upgrade: Supabase PostgreSQL (run CREATE_TABLE_SQL in SQL Editor first).
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._use_db = False  # Set to True after running CREATE_TABLE_SQL

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _supabase(self):
        if get_supabase:
            return get_supabase()
        raise RuntimeError("Supabase not available")

    # ── Write ──

    def store(self, content: str, importance: float = 0.5,
              keywords: list[str] = None, metadata: dict = None) -> int:
        """Store a memory entry. Auto-promotes to appropriate tier based on importance."""
        if importance >= IMPORTANCE_HIGH:
            tier = "long_term"
        elif importance >= IMPORTANCE_MID:
            tier = "short_term"
        else:
            tier = "working"

        if not keywords:
            keywords = _extract_keywords(content)

        # Generate embedding for semantic search
        embedding = generate_embedding(content)

        entry = {
            "id": int(time.time() * 1000000),
            "tier": tier,
            "content": content,
            "keywords": keywords,
            "embedding": embedding,
            "importance": importance,
            "access_count": 0,
            "created_at": self._now(),
            "metadata": metadata or {},
        }

        if self._use_db:
            try:
                row = {**entry, "agent_id": self.agent_id,
                       "embedding": _json.dumps([]),
                       "expires_at": None, "last_accessed": self._now()}
                self._supabase().table(TABLE).insert(row).execute()
                return entry["id"]
            except Exception:
                pass  # Fall through to file storage

        # File storage
        memories = _load_memories(self.agent_id)
        memories.append(entry)
        # Keep last 500 memories max
        if len(memories) > 500:
            memories = memories[-500:]
        _save_memories(self.agent_id, memories)
        return entry["id"]

    # ── Read ──

    def recall(self, query: str = None, limit: int = 5,
               min_importance: float = 0.0, smart: bool = True) -> list[dict]:
        """Recall memories relevant to query. Without query, returns most recent important ones."""
        if self._use_db:
            try:
                resp = self._supabase().table(TABLE).select("*") \
                    .eq("agent_id", self.agent_id) \
                    .gte("importance", min_importance) \
                    .order("importance", desc=True) \
                    .limit(limit * 3).execute()
                if resp and resp.data:
                    memories = resp.data
                    if smart and query:
                        queries = self._expand_query(query)
                        all_ranked = []
                        for q in queries:
                            s = [(self._score(m, q), m) for m in memories]
                            s.sort(key=lambda x: x[0], reverse=True)
                            all_ranked.append([m for _, m in s[:limit * 3]])
                        if len(queries) > 1:
                            memories = self._rrf_fusion(all_ranked)
                        else:
                            memories = all_ranked[0] if all_ranked else []
                        memories = self._mmr_rerank(memories, query, lambda_param=0.7, limit=limit)
                        scored = [(1.0, m) for m in memories]
                    else:
                        scored = [(self._score(m, query), m) for m in memories]
                    scored.sort(key=lambda x: x[0], reverse=True)
                    return [m for _, m in scored[:limit]]
            except Exception:
                pass

        # File storage
        memories = _load_memories(self.agent_id)
        if not memories:
            return []

        # Filter by importance and temporal validity
        memories = [m for m in memories
                    if m.get("importance", 0) >= min_importance
                    and self.is_valid(m)]

        # Score and sort — Smart Retrieval (multi-query + RRF + MMR)
        if smart and query:
            queries = self._expand_query(query)
            all_ranked = []
            for q in queries:
                scored = [(self._score(m, q), m) for m in memories]
                scored.sort(key=lambda x: x[0], reverse=True)
                all_ranked.append([m for _, m in scored[:limit * 3]])
            if len(queries) > 1:
                memories = self._rrf_fusion(all_ranked)
            else:
                memories = all_ranked[0] if all_ranked else []
            memories = self._mmr_rerank(memories, query, lambda_param=0.7, limit=limit)
        else:
            scored = [(self._score(m, query), m) for m in memories]
            scored.sort(key=lambda x: x[0], reverse=True)
            memories = [m for _, m in scored[:limit]]

        # Update access count
        for m in memories[:limit]:
            m["access_count"] = m.get("access_count", 0) + 1
        _save_memories(self.agent_id, memories)

        return memories[:limit]

    def recall_recent(self, hours: float = 24, limit: int = 10) -> list[dict]:
        """Recall recent memories within time window."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        memories = _load_memories(self.agent_id)
        recent = [m for m in memories if m.get("created_at", "") >= cutoff]
        recent.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return recent[:limit]

    # ── Scoring ──

    def _score(self, memory: dict, query: str = None) -> float:
        """Score a memory for relevance: vector similarity + importance × time_decay."""
        importance = memory.get("importance", 0.5)
        created_at = memory.get("created_at", self._now())

        # Time decay
        try:
            age_hours = (datetime.now(timezone.utc) -
                        datetime.fromisoformat(created_at.replace("Z", "+00:00"))).total_seconds() / 3600
        except Exception:
            age_hours = 0

        tier = memory.get("tier", "working")
        half_life = {"working": WM_HALF_LIFE, "short_term": STM_HALF_LIFE,
                     "long_term": LTM_HALF_LIFE}.get(tier, WM_HALF_LIFE)
        time_score = 2.71828 ** (-age_hours / max(half_life, 1))

        # Semantic relevance — dominates the score for queries
        sim_score = 0.5  # Default baseline with no query
        if query:
            stored_emb = memory.get("embedding")
            if stored_emb and isinstance(stored_emb, list) and len(stored_emb) > 0:
                query_emb = generate_embedding(query)
                if query_emb:
                    sim = cosine_similarity(stored_emb, query_emb)
                    # Scale similarity to [0.1, 1.0] for wider impact
                    sim_score = 0.1 + 0.9 * max(sim, 0)
            else:
                # Fallback to keyword matching
                keywords = memory.get("keywords", [])
                query_words = set(_tokenize(query))
                if keywords and query_words:
                    overlap = len(set(k.lower() for k in keywords) & query_words)
                    sim_score = 0.1 + (0.9 * min(overlap / max(len(query_words), 1), 1.0))

        # Recency bonus
        access_count = memory.get("access_count", 0)
        recency_bonus = min(access_count * 0.02, 0.1)

        # Final: similarity (primary) × importance (secondary) × time (decay)
        return sim_score * 2.0 + importance * 0.3 + time_score * 0.2 + recency_bonus

    
    # ── Smart Retrieval (ruflo SmartRetrieval: multi-query + RRF + MMR) ──

    def _expand_query(self, query: str) -> list:
        """Generate 2-3 query variants for multi-angle semantic search."""
        variants = [query]
        words = query.strip().split()
        if not words:
            return variants

        stop_words = {"的","了","是","在","我","你","他","她","它","们","有","和","与","或",
                      "这","那","什么","怎么","为什么","哪个","哪里","一个","这个","那个",
                      "不","也","就","都","很","要","会","可以","能","应该","需要"}
        content_words = [w for w in words if w not in stop_words]
        if len(content_words) >= 2:
            variants.append(" ".join(content_words[:5]))

        synonym_map = {
            "市场": ["行情","走势","趋势"],
            "股票": ["A股","股市","个股"],
            "经济": ["宏观","GDP","增长"],
            "AI": ["人工智能","大模型","LLM"],
            "品牌": ["商标","知名度","口碑"],
            "价格": ["定价","费用","成本"],
            "投资": ["理财","资产","配置"],
            "风险": ["危机","不确定性","波动"],
            "数据": ["统计","指标","数字"],
            "技术": ["科技","创新","研发"],
        }
        for kw, synonyms in synonym_map.items():
            if kw in query:
                for syn in synonyms[:2]:
                    variants.append(query.replace(kw, syn))
                break

        return variants[:3]

    def _rrf_fusion(self, ranked_lists: list, k: int = 60) -> list:
        """Reciprocal Rank Fusion - merge multiple ranked lists into one."""
        scores = {}
        id_to_mem = {}
        for lst in ranked_lists:
            for rank, mem in enumerate(lst):
                mid = mem.get("id", id(mem))
                id_to_mem[mid] = mem
                scores[mid] = scores.get(mid, 0) + 1.0 / (k + rank + 1)
        merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [id_to_mem[mid] for mid, _ in merged]

    def _mmr_rerank(self, results: list, query: str, lambda_param: float = 0.7, limit: int = 10) -> list:
        """Maximal Marginal Relevance - balance relevance (70%) vs diversity (30%)."""
        if len(results) <= limit:
            return results

        kw_sets = []
        for m in results:
            kws = set(m.get("keywords", []) or [])
            content = m.get("content", "")
            kws.update(content[:100].split())
            kw_sets.append(kws)

        selected = [results[0]]
        selected_idx = {0}
        selected_kws = kw_sets[0].copy()

        while len(selected) < min(limit, len(results)):
            best_score, best_idx = -float("inf"), -1
            for i, _ in enumerate(results):
                if i in selected_idx:
                    continue
                relevance = 1.0 / (i + 1)
                overlap = len(kw_sets[i] & selected_kws)
                union = len(kw_sets[i] | selected_kws)
                diversity = 1.0 - (overlap / max(union, 1))
                mmr = lambda_param * relevance + (1 - lambda_param) * diversity
                if mmr > best_score:
                    best_score, best_idx = mmr, i
            if best_idx >= 0:
                selected.append(results[best_idx])
                selected_idx.add(best_idx)
                selected_kws |= kw_sets[best_idx]

        return selected


    
    # ── Temporal Validity (ruflo Tiered Memory) ──

    def is_valid(self, memory: dict, now_ts: str = None) -> bool:
        """Check if a memory is still temporally valid. Superseded/expired = invalid."""
        if now_ts is None:
            now_ts = self._now()
        valid_until = memory.get("valid_until")
        if valid_until and valid_until < now_ts:
            return False
        if memory.get("superseded_by"):
            return False
        return True

    def supersede(self, old_id, new_content: str, importance: float = None,
                  keywords: list = None) -> dict:
        """Create a new memory that supersedes an old one (old stays, marked invalid)."""
        memories = _load_memories(self.agent_id)
        old_mem = None
        for m in memories:
            if m.get("id") == old_id:
                old_mem = m
                break
        if not old_mem:
            return None
        return self.store(
            content=new_content,
            importance=importance or old_mem.get("importance", 0.5),
            tier=old_mem.get("tier", "working"),
            keywords=keywords or old_mem.get("keywords", []),
            supersedes=str(old_id),
        )

    def sweep_expired(self) -> int:
        """Remove expired/superseded memories. Returns count removed."""
        memories = _load_memories(self.agent_id)
        now = self._now()
        valid = []
        removed = 0
        for m in memories:
            if self.is_valid(m, now):
                valid.append(m)
            else:
                removed += 1
        if removed > 0:
            _save_memories(self.agent_id, valid)
        return removed


    
    # ── Consolidation (ruflo Consolidator: sweep → dedup → compact) ──

    def consolidate(self, dedup_strategy: str = "keep-newest") -> dict:
        """Periodic memory maintenance: sweep expired, dedup similar, compact.
        Returns {swept, merged, compacted} counts.
        """
        memories = _load_memories(self.agent_id)
        before = len(memories)
        if not memories:
            return {"swept": 0, "merged": 0, "compacted": 0}

        # Step 1: Sweep — remove expired/invalid
        now = self._now()
        valid = [m for m in memories if self.is_valid(m, now)]
        swept = before - len(valid)

        # Step 2: Dedup — merge similar memories by content overlap
        merged = 0
        seen_hashes = {}
        deduped = []
        for m in valid:
            content_hash = str(hash(m.get("content", "")[:200]))
            if content_hash in seen_hashes:
                existing = seen_hashes[content_hash]
                if dedup_strategy == "keep-newest":
                    if m.get("created_at", "") > existing.get("created_at", ""):
                        # Replace: mark old as superseded
                        existing["valid_until"] = now
                        existing["superseded_by"] = m.get("id")
                        seen_hashes[content_hash] = m
                        deduped.append(m)
                        merged += 1
                    else:
                        m["valid_until"] = now
                        m["superseded_by"] = existing.get("id")
                        merged += 1
                elif dedup_strategy == "merge-tags":
                    # Merge keywords from duplicate into original
                    ek = set(existing.get("keywords", []) or [])
                    mk = set(m.get("keywords", []) or [])
                    existing["keywords"] = list(ek | mk)
                    m["valid_until"] = now
                    m["superseded_by"] = existing.get("id")
                    merged += 1
                # keep-oldest: skip new entry
                else:
                    m["valid_until"] = now
                    m["superseded_by"] = existing.get("id")
                    merged += 1
            else:
                seen_hashes[content_hash] = m
                deduped.append(m)

        # Step 3: Compact — remove very old, low-importance, never-accessed
        compacted = 0
        if len(deduped) > 1000:
            # Sort by score: importance * access_count
            scored = [(m.get("importance", 0) * (m.get("access_count", 0) + 1), m) for m in deduped]
            scored.sort(key=lambda x: x[0])
            # Remove bottom 20% if they're old (>30 days) and never accessed
            cutoff = len(scored) // 5
            to_keep = []
            for i, (score, m) in enumerate(scored):
                if i < cutoff and m.get("access_count", 0) == 0:
                    age_days = 0
                    try:
                        created = m.get("created_at", now)
                        age_days = (datetime.now(timezone.utc) -
                                   datetime.fromisoformat(created.replace("Z", "+00:00"))).days
                    except Exception:
                        pass
                    if age_days > 30:
                        compacted += 1
                        continue
                to_keep.append(m)
            deduped = to_keep

        _save_memories(self.agent_id, deduped)

        return {"swept": swept, "merged": merged, "compacted": compacted,
                "before": before, "after": len(deduped)}


    # ── Maintenance ──

    def promote(self, memory_id: int, new_importance: float = None, new_tier: str = None):
        """Promote a memory to higher tier/increased importance."""
        memories = _load_memories(self.agent_id)
        for m in memories:
            if m.get("id") == memory_id:
                if new_importance:
                    m["importance"] = new_importance
                if new_tier:
                    m["tier"] = new_tier
                break
        _save_memories(self.agent_id, memories)

    def forget(self, memory_id: int = None, before_hours: float = None, max_importance: float = 0.3):
        """Delete memories: specific id, or old/low-importance."""
        memories = _load_memories(self.agent_id)
        if memory_id:
            memories = [m for m in memories if m.get("id") != memory_id]
        elif before_hours:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=before_hours)).isoformat()
            memories = [m for m in memories
                       if not (m.get("created_at", "") < cutoff.isoformat()
                               and m.get("importance", 0) < max_importance)]
        _save_memories(self.agent_id, memories)

    def consolidate(self):
        """Consolidate: delete old low-importance WM, promote important WM to STM."""
        memories = _load_memories(self.agent_id)
        now = datetime.now(timezone.utc)
        wm_cutoff = (now - timedelta(hours=WM_TTL_HOURS)).isoformat()
        kept = []
        for m in memories:
            created = m.get("created_at", "")
            tier = m.get("tier", "working")
            importance = m.get("importance", 0)
            if tier == "working" and created < wm_cutoff and importance < IMPORTANCE_MID:
                continue  # Delete: old, low-importance working memory
            if tier == "working" and importance >= IMPORTANCE_MID:
                m["tier"] = "short_term"  # Promote
            kept.append(m)
        _save_memories(self.agent_id, kept)

    # ── Stats ──

    def stats(self) -> dict:
        """Memory statistics per tier."""
        memories = _load_memories(self.agent_id)
        tiers = {}
        for m in memories:
            t = m.get("tier", "working")
            tiers[t] = tiers.get(t, 0) + 1
        return {"agent_id": self.agent_id, "total": len(memories), "by_tier": tiers}


# ── Helpers ──

def _extract_keywords(text: str, max_kw: int = 8) -> list[str]:
    """Extract simple keywords from text (Chinese + English)."""
    # Chinese: split by common delimiters, take 2-4 char segments
    words = []
    # English words
    eng = re.findall(r'[a-zA-Z]{3,}', text)
    words.extend(w.lower() for w in eng)
    # Chinese 2-gram segments (simple bigram)
    chinese = re.findall(r'[一-鿿]{2,4}', text)
    words.extend(chinese)
    # Deduplicate and limit
    seen = set()
    result = []
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower())
            result.append(w.lower())
    return result[:max_kw]


def _tokenize(text: str) -> set[str]:
    """Tokenize text for keyword matching."""
    return set(_extract_keywords(text, max_kw=20))
