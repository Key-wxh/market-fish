"""
Stack Overflow Fetcher — weekly tag trends and developer ecosystem signals.
Free API, 10000 req/day with key, 300/day without.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from engine.ingestion.base_fetcher import BaseFetcher


class StackOverflowFetcher(BaseFetcher):
    """Fetches SO tag statistics — developer mindshare signals."""

    def __init__(self, data_lake_root: str = None):
        super().__init__("stackoverflow", data_lake_root)
        self.key = os.getenv("STACKEXCHANGE_KEY", "")
        self.base_url = "https://api.stackexchange.com/2.3"

    def _get(self, path: str) -> dict:
        sep = "&" if "?" in path else "?"
        if self.key:
            path = f"{path}{sep}key={self.key}"
        else:
            path = f"{path}{sep}site=stackoverflow"
            if "site=" not in path:
                path += "&site=stackoverflow"

        url = f"{self.base_url}{path}" if path.startswith("/") else path
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MarketFish/5.0"})
            # gzip compression
            req.add_header("Accept-Encoding", "gzip")
            with urllib.request.urlopen(req, timeout=15) as resp:
                import gzip as gz
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gz.decompress(data)
                return {"status": "ok", "data": json.loads(data.decode())}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def fetch(self) -> dict:
        """Fetch top 30 tags with question counts for the week."""
        result = self._get("/tags?order=desc&sort=popular&pagesize=30&fromdate={from_date}&todate={to_date}"
                          .format(
                              from_date=int(datetime.now(timezone.utc).timestamp()) - 7 * 86400,
                              to_date=int(datetime.now(timezone.utc).timestamp()),
                          ))

        if result["status"] != "ok":
            return result

        items = result["data"].get("items", [])
        tags = []
        total_questions = 0
        ai_tags = {"python", "machine-learning", "deep-learning", "nlp", "tensorflow",
                    "pytorch", "artificial-intelligence", "llm", "gpt", "openai",
                    "langchain", "huggingface", "transformer", "neural-network",
                    "chatgpt", "claude", "deepseek", "rag", "embeddings"}

        ai_count = 0
        for item in items:
            name = item.get("name", "")
            count = item.get("count", 0)
            total_questions += count
            is_ai = name in ai_tags or any(kw in name for kw in
                    ["ai", "llm", "ml", "gpt", "agent", "embed", "langchain"])
            if is_ai:
                ai_count += count

            tags.append({
                "name": name,
                "weekly_questions": count,
                "has_synonyms": item.get("has_synonyms", False),
                "is_ai_related": is_ai,
            })

        return {
            "status": "ok",
            "data": {
                "total_weekly_questions": total_questions,
                "ai_related_questions": ai_count,
                "ai_question_ratio": round(ai_count / max(total_questions, 1), 3),
                "tags": tags,
            },
            "metadata": {
                "api_quota_remaining": result["data"].get("quota_remaining", "unknown"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        }

    def validate(self, raw_data: dict) -> tuple[bool, list[str]]:
        warnings = []
        if raw_data.get("status") != "ok":
            return False, [f"API error: {raw_data.get('error', 'unknown')}"]

        data = raw_data.get("data", {})
        tags = data.get("tags", [])

        if len(tags) == 0:
            warnings.append("Zero tags returned — API may be down or rate limited")
        if len(tags) < 20:
            warnings.append(f"Only {len(tags)} tags — expected 30")

        # Real data check: SO should always return high volumes
        if data.get("total_weekly_questions", 0) < 1000:
            warnings.append("Suspiciously low question count — possible API error")

        return True, warnings
