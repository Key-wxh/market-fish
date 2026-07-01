"""
Product Hunt Fetcher — daily launches, votes, topics. GraphQL API, free dev token.
"""
import json, os, urllib.request, urllib.error
from datetime import datetime, timezone
from engine.ingestion.base_fetcher import BaseFetcher

AI_KW = ["ai", "llm", "gpt", "agent", "ml", "chatgpt", "openai", "automation", "nocode", "devtool"]


class ProductHuntFetcher(BaseFetcher):
    def __init__(self, data_lake_root=None):
        super().__init__("producthunt", data_lake_root)
        self.token = os.getenv("PRODUCTHUNT_TOKEN", "")

    def _gql(self, query):
        if not self.token:
            return {"status": "error", "error": "PRODUCTHUNT_TOKEN not set"}
        data = json.dumps({"query": query}).encode()
        req = urllib.request.Request("https://api.producthunt.com/v2/api/graphql", data=data,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "MarketFish/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def fetch(self):
        q = 'query { posts(first:50, order:VOTES) { edges { node { id name tagline description votesCount commentsCount url createdAt topics { edges { node { name } } } } } } }'
        r = self._gql(q)
        if r.get("status") == "error": return r

        edges = r.get("data", {}).get("posts", {}).get("edges", [])
        posts, topics_cnt, ai_cnt, total_v = [], {}, 0, 0
        for e in edges:
            n = e["node"]
            v = n.get("votesCount", 0); total_v += v
            tps = [t["node"]["name"] for t in n.get("topics", {}).get("edges", [])]
            for t in tps: topics_cnt[t.lower()] = topics_cnt.get(t.lower(), 0) + 1
            is_ai = any(k in f"{n.get('name','')} {n.get('tagline','')} {n.get('description','')}".lower() for k in AI_KW) or any(k in tp.lower() for tp in tps for k in AI_KW)
            if is_ai: ai_cnt += 1
            posts.append({"name": n.get("name"), "tagline": n.get("tagline"), "votes": v, "comments": n.get("commentsCount", 0), "url": n.get("url"), "topics": tps, "is_ai": is_ai})

        top_t = sorted(topics_cnt.items(), key=lambda x: x[1], reverse=True)[:12]
        return {"status": "ok", "data": {
            "total_launches": len(posts), "total_votes": total_v, "avg_votes": round(total_v/max(len(posts),1), 1),
            "ai_launches": ai_cnt, "ai_ratio": round(ai_cnt/max(len(posts),1), 2),
            "hot_topics": [{"topic": k, "count": v} for k, v in top_t if v > 1],
            "top_launches": sorted(posts, key=lambda p: p["votes"], reverse=True)[:12],
        }, "metadata": {"fetched_at": datetime.now(timezone.utc).isoformat(), "source": "ProductHunt GraphQL"}}

    def validate(self, raw_data):
        if raw_data.get("status") != "ok": return False, [f"API error: {raw_data.get('error', '?')}"]
        w = []
        if raw_data["data"].get("total_launches", 0) == 0: w.append("Zero launches today")
        return True, w
