"""
GitHub Fetcher — daily trending repositories and topic velocity.
Free API, 60 req/hr without token, 5000/hr with token.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from engine.ingestion.base_fetcher import BaseFetcher


class GitHubFetcher(BaseFetcher):
    """Fetches GitHub trending repos and topic statistics."""

    def __init__(self, data_lake_root: str = None):
        super().__init__("github", data_lake_root)
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.base_url = "https://api.github.com"

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json", "User-Agent": "MarketFish/5.0"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _api_get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {"status": "ok", "data": json.loads(resp.read().decode())}
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200] if e.fp else ""
            return {"status": "error", "error": f"HTTP {e.code}: {body}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def fetch(self) -> dict:
        """Fetch trending repos created in last 7 days, sorted by stars."""
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        url = f"{self.base_url}/search/repositories?q=created:>{since}&sort=stars&order=desc&per_page=50"

        search_result = self._api_get(url)
        if search_result["status"] != "ok":
            return search_result

        repos = search_result["data"].get("items", [])

        # Extract key signals
        topics_count = {}
        languages_count = {}
        total_stars = 0
        processed = []

        for repo in repos:
            stars = repo.get("stargazers_count", 0)
            lang = repo.get("language") or "unknown"
            total_stars += stars
            languages_count[lang] = languages_count.get(lang, 0) + 1

            for topic in repo.get("topics", []):
                topics_count[topic] = topics_count.get(topic, 0) + 1

            processed.append({
                "full_name": repo.get("full_name"),
                "description": repo.get("description"),
                "language": lang,
                "stars": stars,
                "forks": repo.get("forks_count", 0),
                "topics": repo.get("topics", []),
                "created_at": repo.get("created_at"),
                "url": repo.get("html_url"),
            })

        # Sort topics and languages by frequency
        top_topics = sorted(topics_count.items(), key=lambda x: x[1], reverse=True)[:20]
        top_languages = sorted(languages_count.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "status": "ok",
            "data": {
                "period": f"{since}..today",
                "total_repos": search_result["data"].get("total_count", 0),
                "total_stars": total_stars,
                "trending_repos": processed[:50],
                "hot_topics": [{"name": k, "count": v} for k, v in top_topics],
                "language_distribution": [{"language": k, "count": v} for k, v in top_languages],
                "ai_ml_count": sum(1 for t, c in topics_count.items()
                                   if any(kw in t.lower() for kw in ("ai", "ml", "llm", "gpt", "machine-learning", "deep-learning", "agent"))),
            },
            "metadata": {
                "api_url": url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "rate_limit_remaining": search_result["data"].get("rate_limit", "unknown"),
            }
        }

    def validate(self, raw_data: dict) -> tuple[bool, list[str]]:
        """Validate the API response has expected structure."""
        warnings = []
        if raw_data.get("status") != "ok":
            return False, [f"API error: {raw_data.get('error', 'unknown')}"]

        data = raw_data.get("data", {})
        repos = data.get("trending_repos", [])

        if len(repos) == 0:
            warnings.append("Zero trending repos returned — possible API issue")
        if len(repos) < 10:
            warnings.append(f"Only {len(repos)} repos — expected at least 10")

        # Real data check: GitHub should never return zero total repos
        if data.get("total_repos", 0) == 0:
            warnings.append("total_repos is 0 — suspicious, might indicate API rate limit")

        return True, warnings
