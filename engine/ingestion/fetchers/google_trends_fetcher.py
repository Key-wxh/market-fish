"""
Google Trends Fetcher — search interest for key technology/business keywords.
Free, no API key. Uses pytrends (unofficial library).
Keywords represent proxy demand signals for market categories.
"""
import json
from datetime import datetime, timezone
from engine.ingestion.base_fetcher import BaseFetcher

# Keywords mapped to market dimensions
KEYWORDS = {
    "ai_tools": ["AI tools", "AI agent", "ChatGPT alternative"],
    "saas": ["SaaS", "no-code", "low-code"],
    "freelance": ["freelance platform", "Upwork", "remote work"],
    "startup": ["startup funding", "how to start a business", "side hustle"],
    "dev_tools": ["API", "developer tools", "open source"],
}


class GoogleTrendsFetcher(BaseFetcher):
    def __init__(self, data_lake_root=None):
        super().__init__("google_trends", data_lake_root)

    def fetch(self):
        try:
            from pytrends.request import TrendReq
        except ImportError:
            return {"status": "error", "error": "pytrends not installed. pip install pytrends"}

        try:
            pytrends = TrendReq(hl="en-US", tz=360, timeout=10)
        except Exception as e:
            return {"status": "error", "error": f"pytrends init failed: {e}"}

        results = {}
        errors = []
        total_interest = 0
        count = 0

        for category, kw_list in KEYWORDS.items():
            try:
                pytrends.build_payload(kw_list, timeframe="today 3-m", geo="")
                interest = pytrends.interest_over_time()
                if interest is not None and not interest.empty:
                    latest = interest.iloc[-1].to_dict()
                    avg_val = round(sum(v for k, v in latest.items() if k != "isPartial") / max(len(latest) - 1, 1), 1)
                    results[category] = {
                        "keywords": kw_list,
                        "latest_values": {k: v for k, v in latest.items() if k != "isPartial"},
                        "average_interest": avg_val,
                    }
                    total_interest += avg_val
                    count += 1
            except Exception as e:
                errors.append(f"{category}: {e}")

        # Build summary signals
        overall_interest = round(total_interest / max(count, 1), 1) if count > 0 else 0
        ai_interest = results.get("ai_tools", {}).get("average_interest", 0)

        return {"status": "ok" if count > 0 else "error", "data": {
            "categories_tracked": count,
            "total_categories": len(KEYWORDS),
            "overall_interest_index": overall_interest,
            "ai_interest_index": ai_interest,
            "categories": results,
            "errors": errors,
        }, "metadata": {"fetched_at": datetime.now(timezone.utc).isoformat(), "source": "Google Trends via pytrends"}}

    def validate(self, raw_data):
        if raw_data.get("status") != "ok":
            return False, [f"Error: {raw_data.get('error','?')}"]
        count = raw_data["data"].get("categories_tracked", 0)
        if count == 0:
            return False, ["No categories tracked — pytrends may be blocked"]
        return True, []
