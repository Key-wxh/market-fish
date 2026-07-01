"""
Hacker News Fetcher — daily top stories and AI/tech sentiment.
Official Firebase API, completely free, no rate limit, no auth.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from engine.ingestion.base_fetcher import BaseFetcher

# Keywords for topic classification
TECH_KEYWORDS = [
    "ai", "llm", "gpt", "openai", "claude", "deepseek", "chatgpt",
    "machine learning", "deep learning", "neural", "transformer",
    "python", "rust", "go", "javascript", "typescript", "wasm",
    "startup", "funding", "yc", "saas", "open source", "github",
    "database", "postgres", "sqlite", "kubernetes", "docker",
    "security", "crypto", "bitcoin", "blockchain", "web3",
    "apple", "google", "microsoft", "meta", "amazon", "nvidia",
    "browser", "web", "api", "devtools", "cli", "terminal",
    "show hn", "ask hn", "launch", "beta", "hiring",
]

AI_KEYWORDS = ["ai", "llm", "gpt", "openai", "claude", "deepseek", "chatgpt",
               "machine learning", "deep learning", "neural", "transformer",
               "agent", "rag", "embedding", "fine-tuning", "prompt"]


class HackerNewsFetcher(BaseFetcher):
    """Fetches HN top stories, classifies topics, computes rough sentiment."""

    def __init__(self, data_lake_root: str = None):
        super().__init__("hackernews", data_lake_root)
        self.base_url = "https://hacker-news.firebaseio.com/v0"

    def _get(self, endpoint: str) -> dict:
        url = f"{self.base_url}/{endpoint}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MarketFish/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                return {"status": "ok", "data": data}
        except Exception as e:
            return {"status": "error", "error": str(e), "url": url}

    def fetch(self) -> dict:
        """Fetch top stories with metadata for topic classification."""
        # Step 1: Get top story IDs
        top_result = self._get("topstories.json")
        if top_result["status"] != "ok":
            return top_result

        story_ids = top_result["data"][:100]  # Top 100 stories

        # Step 2: Fetch story details (up to 50, to stay fast)
        stories = []
        errors = 0
        for sid in story_ids[:50]:
            item_result = self._get(f"item/{sid}.json")
            if item_result["status"] == "ok" and item_result["data"]:
                item = item_result["data"]
                if item.get("type") == "story":
                    stories.append(item)
            else:
                errors += 1

        # Step 3: Classify topics and compute signals
        total_score = 0
        total_comments = 0
        topic_hits = {kw: 0 for kw in TECH_KEYWORDS}
        ai_hits = 0
        classified_stories = []

        for story in stories:
            title = (story.get("title", "") or "").lower()
            url = story.get("url", "") or ""
            score = story.get("score", 0) or 0
            descendants = story.get("descendants", 0) or 0

            total_score += score
            total_comments += descendants

            # Topic classification
            matched_topics = []
            is_ai = False
            for kw in TECH_KEYWORDS:
                if kw in title:
                    topic_hits[kw] += 1
                    matched_topics.append(kw)
                if kw in AI_KEYWORDS and kw in title:
                    is_ai = True

            if is_ai:
                ai_hits += 1

            classified_stories.append({
                "id": story.get("id"),
                "title": story.get("title"),
                "url": story.get("url"),
                "score": score,
                "comments": descendants,
                "by": story.get("by"),
                "time": story.get("time"),
                "topics": matched_topics,
                "is_ai_related": is_ai,
            })

        # Sort topic hits
        top_topics = sorted(topic_hits.items(), key=lambda x: x[1], reverse=True)[:15]
        top_topics = [(k, v) for k, v in top_topics if v > 0]

        # Simple sentiment: high-score AI stories / total AI stories
        ai_stories = [s for s in classified_stories if s["is_ai_related"]]
        avg_ai_score = sum(s["score"] for s in ai_stories) / max(len(ai_stories), 1)
        overall_avg_score = total_score / max(len(classified_stories), 1)

        # Sentiment score: AI stories performing above average = bullish
        sentiment = round((avg_ai_score / max(overall_avg_score, 1) - 1), 2) if ai_stories else 0

        return {
            "status": "ok",
            "data": {
                "stories_fetched": len(classified_stories),
                "total_score": total_score,
                "total_comments": total_comments,
                "ai_stories": ai_hits,
                "ai_story_ratio": round(ai_hits / max(len(classified_stories), 1), 2),
                "avg_story_score": round(overall_avg_score, 1),
                "avg_ai_score": round(avg_ai_score, 1),
                "sentiment_score": sentiment,
                "hot_topics": [{"topic": k, "hits": v} for k, v in top_topics],
                "top_stories": classified_stories[:20],
            },
            "metadata": {
                "story_ids_available": len(story_ids),
                "fetch_errors": errors,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        }

    def validate(self, raw_data: dict) -> tuple[bool, list[str]]:
        warnings = []
        if raw_data.get("status") != "ok":
            return False, [f"API error: {raw_data.get('error', 'unknown')}"]

        data = raw_data.get("data", {})
        stories = data.get("stories_fetched", 0)

        if stories == 0:
            warnings.append("Zero stories fetched — HN API may be down")
        if stories < 10:
            warnings.append(f"Only {stories} stories — expected 50, HN API rate limit?")

        return True, warnings
