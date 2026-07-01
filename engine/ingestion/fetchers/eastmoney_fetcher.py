"""
China Market Fetcher — via ChainGold (seobrief.cc) + EastMoney CPI directly.
Works from both HK (localhost:3002) and domestic (seobrief.cc) servers.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from engine.ingestion.base_fetcher import BaseFetcher


class EastMoneyFetcher(BaseFetcher):
    """Fetches Chinese market data via ChainGold API + EastMoney CPI."""

    def __init__(self, data_lake_root: str = None):
        super().__init__("eastmoney", data_lake_root)
        # Try localhost first (HK), fall back to public URL (domestic)
        self.chaingold_urls = [
            "http://localhost:3002/api/serenity",
            "https://seobrief.cc/api/serenity",
        ]

    def _chaingold_get(self, path: str) -> dict:
        """Call ChainGold API, trying localhost first then public URL."""
        for base in self.chaingold_urls:
            try:
                url = f"{base}/{path}"
                req = urllib.request.Request(url, headers={"User-Agent": "MarketFish/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode())
            except Exception:
                continue
        return {"success": False, "error": "All ChainGold URLs failed"}

    def _fetch_cpi_direct(self) -> dict:
        """Fetch CPI from EastMoney data center (works from domestic)."""
        url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
               "?reportName=RPT_ECONOMY_CPI"
               "&columns=REPORT_DATE,TIME,NATIONAL_SAME,NATIONAL_BASE,NATIONAL_SEQUENTIAL,NATIONAL_ACCUMULATE"
               "&pageSize=3&pageNumber=1&sortTypes=-1&sortColumns=REPORT_DATE")
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://data.eastmoney.com/",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                items = data.get("result", {}).get("data", [])
                cpi_values = []
                for it in items:
                    cpi_values.append({
                        "date": it.get("REPORT_DATE", "")[:10],
                        "period": it.get("TIME", ""),
                        "yoy_pct": it.get("NATIONAL_SAME"),  # 同比
                        "base_index": it.get("NATIONAL_BASE"),  # 定基指数
                    })
                return cpi_values
        except Exception:
            return []

    def fetch(self) -> dict:
        """Fetch industry data from ChainGold + CPI from EastMoney."""
        # Industries from ChainGold
        ind_data = self._chaingold_get("industries")
        industries = ind_data.get("data", {}).get("industries", [])

        # Benchmark kline from ChainGold
        kline_data = self._chaingold_get("kline?code=002415")
        klines = kline_data.get("data", {}).get("data", {}).get("klines", [])

        # CPI from EastMoney direct
        cpi_values = self._fetch_cpi_direct()

        # Analyze kline trend
        ups = downs = 0
        latest_close = prev_close = None
        for k in klines[-20:]:
            parts = k.split(",")
            if len(parts) >= 3:
                try:
                    close = float(parts[2])
                    open_v = float(parts[1])
                    if close > open_v:
                        ups += 1
                    else:
                        downs += 1
                    latest_close = close
                    if prev_close is None and len(klines) >= 2:
                        prev_close = float(klines[-2].split(",")[2])
                except (ValueError, IndexError):
                    pass

        change_pct = round((latest_close - prev_close) / prev_close * 100, 2) if latest_close and prev_close else None

        # Latest CPI
        latest_cpi = cpi_values[0] if cpi_values else {}

        return {
            "status": "ok",
            "data": {
                "total_industries": len(industries),
                "active_industries": sum(1 for i in industries if i.get("status") == "llm"),
                "total_bottlenecks": sum(i.get("bottlenecks", 0) for i in industries),
                "industries": industries,
                "benchmark_code": "002415",
                "benchmark_latest_close": latest_close,
                "benchmark_latest_change_pct": change_pct,
                "recent_20d_up_ratio": round(ups / max(ups + downs, 1), 2),
                "kline_count": len(klines),
                "cpi_yoy_pct": latest_cpi.get("yoy_pct"),
                "cpi_date": latest_cpi.get("date"),
                "cpi_values": cpi_values,
            },
            "metadata": {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "ChainGold + EastMoney CPI",
            }
        }

    def validate(self, raw_data: dict) -> tuple[bool, list[str]]:
        warnings = []
        if raw_data.get("status") != "ok":
            return False, [f"API error: {raw_data.get('error', 'unknown')}"]

        data = raw_data.get("data", {})
        industries = data.get("total_industries", 0)
        if industries == 0:
            return False, ["Zero industries — ChainGold may be down"]
        if not data.get("benchmark_latest_close"):
            warnings.append("No benchmark price data")

        return True, warnings
