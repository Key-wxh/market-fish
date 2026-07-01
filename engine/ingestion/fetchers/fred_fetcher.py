"""
World Bank Fetcher — 1400+ global macroeconomic indicators, 200+ countries.
Completely free, zero registration, zero API key. Replaces FRED for global coverage.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from engine.ingestion.base_fetcher import BaseFetcher

# Key indicators (validated by academic literature)
INDICATORS = {
    "NY.GDP.MKTP.CD":    {"name": "GDP (current US$)",           "unit": "USD",   "group": "output"},
    "NY.GDP.MKTP.KD.ZG": {"name": "GDP growth (annual %)",       "unit": "pct",   "group": "output"},
    "FP.CPI.TOTL":       {"name": "Consumer Price Index",        "unit": "index", "group": "inflation"},
    "FP.CPI.TOTL.ZG":    {"name": "Inflation (CPI annual %)",    "unit": "pct",   "group": "inflation"},
    "SL.UEM.TOTL.ZS":    {"name": "Unemployment rate",           "unit": "pct",   "group": "labor"},
    "SL.TLF.TOTL.IN":    {"name": "Labor force",                 "unit": "people","group": "labor"},
    "BX.KLT.DINV.WD.GD.ZS": {"name": "FDI (% of GDP)",          "unit": "pct",   "group": "trade"},
    "NE.EXP.GNFS.ZS":    {"name": "Exports (% of GDP)",          "unit": "pct",   "group": "trade"},
    "NY.GNP.PCAP.CD":    {"name": "GNI per capita",             "unit": "USD",   "group": "income"},
    "SP.POP.TOTL":       {"name": "Population",                  "unit": "people","group": "demographic"},
    "IT.NET.USER.ZS":    {"name": "Internet users (% population)","unit": "pct",  "group": "tech"},
    "IT.CEL.SETS.P2":    {"name": "Mobile subscriptions (per 100)","unit": "per100","group": "tech"},
}

# Countries: US, China, Japan, Germany, UK, India, EU, World
COUNTRIES = {
    "US": "United States",
    "CN": "China",
    "JP": "Japan",
    "DE": "Germany",
    "GB": "United Kingdom",
    "IN": "India",
    "EU": "European Union",
    "WLD": "World",
}

API_BASE = "https://api.worldbank.org/v2"


class FredFetcher(BaseFetcher):  # Keep class name for backward compat
    """Fetches global macroeconomic indicators from World Bank API.

    No API key needed. Rate limit: ~50 requests/second (very generous).
    Collects 12 indicators × 8 countries = 96 data points per fetch.
    """

    def __init__(self, data_lake_root: str = None):
        super().__init__("fred", data_lake_root)  # Keep source name for silver compat

    def _fetch_indicator(self, indicator: str, country: str) -> dict:
        """Fetch latest values for one indicator + country."""
        url = (f"{API_BASE}/country/{country}/indicator/{indicator}"
               f"?format=json&per_page=3&date=2020:2026")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MarketFish/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())

            if not data or len(data) < 2 or not data[1]:
                return None

            # data[0] = metadata, data[1] = observations array
            observations = data[1]
            values = []
            for obs in observations:
                if obs.get("value"):
                    try:
                        values.append({
                            "year": obs.get("date"),
                            "value": float(obs["value"]),
                        })
                    except (ValueError, TypeError):
                        pass

            if not values:
                return None

            return {
                "indicator": indicator,
                "country": country,
                "country_name": obs.get("country", {}).get("value", country),
                "indicator_name": obs.get("indicator", {}).get("value", indicator),
                "latest": values[0],
                "previous": values[1] if len(values) > 1 else None,
                "two_ago": values[2] if len(values) > 2 else None,
            }

        except Exception:
            return None

    def fetch(self) -> dict:
        """Fetch 12 indicators for 8 countries (~96 data points) in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        errors = []
        fetched = 0
        country_names = dict(COUNTRIES)

        # Build all (country, indicator) tasks
        tasks = []
        for country, cname in COUNTRIES.items():
            for ind_id, ind_info in INDICATORS.items():
                tasks.append((country, cname, ind_id, ind_info))

        # Parallel fetch: 8 workers = 1 per country, polite to World Bank
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(self._fetch_indicator, ind_id, country): (country, ind_id)
                for country, cname, ind_id, ind_info in tasks
            }
            for future in as_completed(futures):
                country, ind_id = futures[future]
                try:
                    result = future.result(timeout=10)
                except Exception:
                    result = None

                if country not in results:
                    results[country] = {"name": country_names.get(country, country), "indicators": {}, "available": 0}

                ind_info = INDICATORS[ind_id]
                if result:
                    results[country]["indicators"][ind_id] = {
                        "name": ind_info["name"],
                        "unit": ind_info["unit"],
                        "group": ind_info["group"],
                        "latest": result["latest"],
                        "previous": result.get("previous"),
                        "two_ago": result.get("two_ago"),
                    }
                    results[country]["available"] += 1
                    fetched += 1
                else:
                    results[country]["indicators"][ind_id] = None

        # Build summary
        summary = {}
        # US GDP growth
        us_gdp = results.get("US", {}).get("indicators", {}).get("NY.GDP.MKTP.KD.ZG")
        if us_gdp and us_gdp.get("latest"):
            summary["us_gdp_growth_pct"] = us_gdp["latest"]["value"]

        # US inflation
        us_cpi = results.get("US", {}).get("indicators", {}).get("FP.CPI.TOTL.ZG")
        if us_cpi and us_cpi.get("latest"):
            summary["us_inflation_pct"] = us_cpi["latest"]["value"]

        # US unemployment
        us_unemp = results.get("US", {}).get("indicators", {}).get("SL.UEM.TOTL.ZS")
        if us_unemp and us_unemp.get("latest"):
            summary["us_unemployment_pct"] = us_unemp["latest"]["value"]

        # China GDP growth
        cn_gdp = results.get("CN", {}).get("indicators", {}).get("NY.GDP.MKTP.KD.ZG")
        if cn_gdp and cn_gdp.get("latest"):
            summary["cn_gdp_growth_pct"] = cn_gdp["latest"]["value"]

        # World GDP growth
        wld_gdp = results.get("WLD", {}).get("indicators", {}).get("NY.GDP.MKTP.KD.ZG")
        if wld_gdp and wld_gdp.get("latest"):
            summary["world_gdp_growth_pct"] = wld_gdp["latest"]["value"]

        status = "ok" if fetched > 20 else ("partial" if fetched > 0 else "error")

        return {
            "status": status,
            "data": {
                "total_indicators": len(INDICATORS),
                "total_countries": len(COUNTRIES),
                "datapoints_fetched": fetched,
                "countries": results,
                "summary": summary,
            },
            "metadata": {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "api.worldbank.org (free, no key)",
                "note": "World Bank data typically has 1-2 year lag on latest values"
            }
        }

    def validate(self, raw_data: dict) -> tuple[bool, list[str]]:
        warnings = []
        status = raw_data.get("status")
        if status not in ("ok", "partial"):
            return False, [f"Fetch failed: {raw_data.get('error', 'unknown')}"]

        data = raw_data.get("data", {})
        fetched = data.get("datapoints_fetched", 0)

        if fetched == 0:
            return False, ["No indicators fetched — API may be down"]
        if fetched < 30:
            warnings.append(f"Only {fetched}/96 expected — possible network issue")

        # Note the data lag
        warnings.append("World Bank data typically 1-2 years behind — use for trend, not real-time")

        return True, warnings
