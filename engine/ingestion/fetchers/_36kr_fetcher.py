"""
36Kr (36氪) RSS Fetcher — Chinese tech/startup news. Free RSS feed, no auth.
"""
import json, urllib.request, urllib.error, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from engine.ingestion.base_fetcher import BaseFetcher

CATEGORY_KW = {
    "ai": ["ai", "人工智能", "大模型", "llm", "gpt", "agent"],
    "funding": ["融资", "天使轮", "a轮", "b轮", "c轮", "投资", "估值", "ipo"],
    "enterprise": ["企业服务", "saas", "数字化", "b2b", "效率"],
    "consumer": ["消费", "电商", "品牌", "零售", "新消费"],
    "hardware": ["芯片", "半导体", "硬件", "机器人", "新能源", "电池"],
    "policy": ["政策", "监管", "法规", "部委", "发改委"],
}


class _36krFetcher(BaseFetcher):
    def __init__(self, data_lake_root=None):
        super().__init__("36kr", data_lake_root)

    def fetch(self):
        try:
            req = urllib.request.Request("https://36kr.com/feed",
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                root = ET.fromstring(r.read().decode("utf-8"))
        except Exception as e:
            return {"status": "error", "error": str(e)}

        items = []
        cat_counts = {k: 0 for k in CATEGORY_KW}
        for item in root.iter("item"):
            title = (item.find("title").text or "") if item.find("title") is not None else ""
            link = (item.find("link").text or "") if item.find("link") is not None else ""
            desc = (item.find("description").text or "") if item.find("description") is not None else ""
            pub = (item.find("pubDate").text or "") if item.find("pubDate") is not None else ""

            # Category classification
            text = f"{title} {desc}".lower()
            cats = []
            for cat, kws in CATEGORY_KW.items():
                if any(k in text for k in kws):
                    cats.append(cat)
                    cat_counts[cat] += 1

            items.append({"title": title, "link": link, "description": desc[:200], "pub_date": pub, "categories": cats})

        top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)
        return {"status": "ok", "data": {
            "total_articles": len(items),
            "category_counts": {k: v for k, v in top_cats},
            "ai_ratio": round(cat_counts.get("ai", 0) / max(len(items), 1), 2),
            "funding_ratio": round(cat_counts.get("funding", 0) / max(len(items), 1), 2),
            "articles": items[:30],
        }, "metadata": {"fetched_at": datetime.now(timezone.utc).isoformat(), "source": "36kr.com/feed"}}

    def validate(self, raw_data):
        if raw_data.get("status") != "ok":
            return False, [f"Error: {raw_data.get('error','?')}"]
        w = []
        n = raw_data["data"].get("total_articles", 0)
        if n == 0: w.append("Zero articles")
        if n < 10: w.append(f"Only {n} articles — feed may be broken")
        return True, w
