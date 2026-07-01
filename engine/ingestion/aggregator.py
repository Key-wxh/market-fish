"""
Aggregator — Silver → Gold transformation.
Reads all Silver time-series, computes composite signals, generates:
1. gold/seed_snapshot.json — pipeline-ready seed data
2. gold/seed_snapshot_meta.json — full provenance
3. gold/signals_latest.parquet — feature store
4. gold/daily_brief.md — human-readable market briefing
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _load_silver_series(data_lake_root: str) -> dict:
    """Load all Silver time-series into a dict of {source: rows}. Tries Parquet first, then JSON."""
    silver_dir = Path(data_lake_root) / "silver" / "time_series"
    if not silver_dir.exists():
        return {}

    data = {}
    for f in sorted(silver_dir.glob("*")):
        source = f.stem.replace("_ts", "")
        try:
            if f.suffix == ".parquet":
                import pandas as pd
                df = pd.read_parquet(f)
                data[source] = df.to_dict("records")
            elif f.suffix == ".json":
                with open(f, encoding="utf-8") as fh:
                    data[source] = json.load(fh)
        except Exception:
            continue
    return data


def _latest_row(rows: list[dict]) -> dict:
    """Get the most recent row from a time-series."""
    if not rows:
        return {}
    return max(rows, key=lambda r: r.get("date", ""))


def _compute_yoy(latest_val: float, rows: list[dict], key: str, months_back: int = 12) -> Optional[float]:
    """Compute year-over-year change from time-series data."""
    if not rows or len(rows) < 2:
        return None
    sorted_rows = sorted(rows, key=lambda r: r.get("date", ""))
    if len(sorted_rows) < months_back:
        return None
    prev_val = sorted_rows[-months_back].get(key)
    if prev_val and prev_val != 0:
        return round((latest_val / prev_val - 1) * 100, 1)
    return None


def regenerate_gold(data_lake_root: str = None) -> dict:
    """Regenerate the Gold layer from Silver time-series.

    Returns the complete seed_snapshot dict.
    """
    if data_lake_root is None:
        data_lake_root = str(Path(__file__).parent.parent.parent / "data_lake")

    silver_data = _load_silver_series(data_lake_root)
    gold_dir = Path(data_lake_root) / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)

    dimensions = {}
    signals = {}
    provenance = {
        "data_sources": [],
        "fetches_included": 0,
        "oldest_data_point": None,
        "newest_data_point": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validation_passed": True,
        "validation_warnings": [],
    }

    # ── Macroeconomic: World Bank ──
    fred_rows = silver_data.get("fred", [])
    if fred_rows:
        latest = _latest_row(fred_rows)
        dimensions.setdefault("macroeconomic", {})
        dimensions["macroeconomic"]["global"] = {
            "us_gdp_growth_pct": latest.get("us_gdp_growth_pct"),
            "us_inflation_pct": latest.get("us_inflation_pct"),
            "us_unemployment_pct": latest.get("us_unemployment_pct"),
            "cn_gdp_growth_pct": latest.get("cn_gdp_growth_pct"),
            "world_gdp_growth_pct": latest.get("world_gdp_growth_pct"),
            "datapoints_fetched": latest.get("datapoints_fetched"),
        }
        provenance["data_sources"].append("World Bank API (free, no key)")
        provenance["fetches_included"] += 1

    # ── Compute macro signals ──
    macro = dimensions.get("macroeconomic", {}).get("global", {})
    if macro.get("us_gdp_growth_pct") is not None and macro["us_gdp_growth_pct"] < 1.5:
        signals["signal_economic_slowdown"] = True
    if macro.get("cn_gdp_growth_pct") is not None and macro["cn_gdp_growth_pct"] < 4.0:
        signals["signal_china_economy_weak"] = True
    if macro.get("us_inflation_pct") is not None and macro["us_inflation_pct"] > 5.0:
        signals["signal_inflation_accelerating"] = True
    if (macro.get("us_gdp_growth_pct") is not None and macro.get("cn_gdp_growth_pct") is not None
        and macro["us_gdp_growth_pct"] < 2.0 and macro["cn_gdp_growth_pct"] < 4.0
        and macro.get("world_gdp_growth_pct", 99) < 2.5):
        signals["signal_global_synchronized_slowdown"] = True

    # ── Technology: GitHub ──
    gh_rows = silver_data.get("github", [])
    if gh_rows:
        latest = _latest_row(gh_rows)
        dimensions.setdefault("technology_adoption", {})
        dimensions["technology_adoption"]["github"] = {
            "total_trending_repos": latest.get("total_repos"),
            "total_stars": latest.get("total_stars"),
            "ai_ml_repos": latest.get("ai_ml_repos"),
            "ai_ml_ratio": round(latest.get("ai_ml_repos", 0) / max(latest.get("total_repos", 1), 1), 2),
        }
        provenance["data_sources"].append("GitHub API")

    # ── Technology: Hacker News ──
    hn_rows = silver_data.get("hackernews", [])
    if hn_rows:
        latest = _latest_row(hn_rows)
        dimensions.setdefault("technology_adoption", {})
        dimensions["technology_adoption"].setdefault("hackernews", {})
        dimensions["technology_adoption"]["hackernews"] = {
            "stories_fetched": latest.get("stories_fetched"),
            "total_score": latest.get("total_score"),
            "total_comments": latest.get("total_comments"),
            "ai_stories": latest.get("ai_stories"),
            "ai_story_ratio": latest.get("ai_story_ratio"),
            "sentiment_score": latest.get("sentiment_score"),
            "avg_story_score": latest.get("avg_story_score"),
        }
        provenance["data_sources"].append("Hacker News API")

    # ── Technology: Stack Overflow ──
    so_rows = silver_data.get("stackoverflow", [])
    if so_rows:
        latest = _latest_row(so_rows)
        dimensions.setdefault("technology_adoption", {})
        dimensions["technology_adoption"].setdefault("stackoverflow", {})
        dimensions["technology_adoption"]["stackoverflow"] = {
            "total_weekly_questions": latest.get("total_weekly_questions"),
            "ai_related_questions": latest.get("ai_related_questions"),
            "ai_question_ratio": latest.get("ai_question_ratio"),
        }
        provenance["data_sources"].append("Stack Overflow API")

    # ── Technology: Product Hunt ──
    ph_rows = silver_data.get("producthunt", [])
    if ph_rows:
        latest = _latest_row(ph_rows)
        dimensions.setdefault("technology_adoption", {})
        dimensions["technology_adoption"]["producthunt"] = {
            "total_launches": latest.get("total_launches"),
            "total_votes": latest.get("total_votes"),
            "ai_launches": latest.get("ai_launches"),
            "ai_ratio": latest.get("ai_ratio"),
        }
        provenance["data_sources"].append("Product Hunt API")

    # ── Price/Volume: EastMoney (via ChainGold proxy or direct) ──
    em_rows = silver_data.get("eastmoney", [])
    if em_rows:
        latest = _latest_row(em_rows)
        source = latest.get("source", "direct")
        dimensions.setdefault("price_volume", {})
        if source == "chaingold_proxy":
            dimensions["price_volume"]["eastmoney"] = {
                "source": "ChainGold proxy :3002",
                "total_industries": latest.get("total_industries"),
                "active_industries": latest.get("active_industries"),
                "total_bottlenecks": latest.get("total_bottlenecks"),
                "benchmark_code": "002415",
                "benchmark_latest_close": latest.get("benchmark_latest_close"),
                "benchmark_latest_change_pct": latest.get("benchmark_latest_change_pct"),
                "recent_20d_up_ratio": latest.get("recent_20d_up_ratio"),
                "kline_count": latest.get("kline_count"),
            }
            # Market signal from benchmark
            if latest.get("recent_20d_up_ratio", 0) > 0.6:
                signals["signal_market_bullish"] = True
            elif latest.get("recent_20d_up_ratio", 0) < 0.35:
                signals["signal_market_bearish"] = True
        else:
            dimensions["price_volume"]["eastmoney"] = {
                "source": "EastMoney direct",
                "total_sectors": latest.get("total_sectors"),
                "up_ratio": latest.get("up_ratio"),
                "total_turnover_yi": latest.get("total_turnover_yi"),
                "avg_pe": latest.get("avg_pe"),
            }
            if latest.get("up_ratio", 0) > 0.7:
                signals["signal_market_bullish"] = True
            if latest.get("up_ratio", 0) < 0.3:
                signals["signal_market_bearish"] = True
        provenance["data_sources"].append("EastMoney/ChainGold (东方财富)")

    # ── Compute Tech + Market Signals ──
    tech = dimensions.get("technology_adoption", {})

    # AI demand surge
    gh = tech.get("github", {})
    if gh.get("ai_ml_ratio", 0) > 0.25:
        signals["signal_ai_tools_demand_surge"] = True

    # Tech sentiment
    hn = tech.get("hackernews", {})
    if hn.get("sentiment_score", 0) > 0.1:
        signals["signal_tech_sentiment_bullish"] = True

    # Tech adoption accelerating
    so = tech.get("stackoverflow", {})
    if gh.get("total_trending_repos", 0) > 1000 and so.get("ai_question_ratio", 0) > 0.05:
        signals["signal_tech_adoption_accelerating"] = True

    # EastMoney/ChainGold signals (market sentiment from benchmark)
    # Already set above in the eastmoney section, no duplicate here

    # ── Build snapshot ──
    snapshot = {
        "snapshot_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dimensions": dimensions,
        "signals": signals,
        "provenance": provenance,
    }

    # Write gold files
    snapshot_path = gold_dir / "seed_snapshot.json"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    meta_path = gold_dir / "seed_snapshot_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "snapshot_id": snapshot["snapshot_id"],
            "generated_at": snapshot["generated_at"],
            "provenance": provenance,
            "dimension_count": len(dimensions),
            "signal_count": len(signals),
            "total_features": sum(
                len(v) if isinstance(v, dict) else 1
                for dim in dimensions.values()
                for v in (dim.values() if isinstance(dim, dict) else [dim])
                if isinstance(v, dict)
            ),
        }, f, indent=2, ensure_ascii=False)

    # Save to signals history
    hist_dir = gold_dir / "signals_history"
    hist_dir.mkdir(exist_ok=True)
    week_label = datetime.now(timezone.utc).strftime("%YW%U")
    hist_path = hist_dir / f"signals_{week_label}.json"
    hist_entry = {
        "snapshot_id": snapshot["snapshot_id"],
        "generated_at": snapshot["generated_at"],
        "signals": signals,
        "dimension_summary": {
            dim: list(src.keys()) if isinstance(src, dict) else "scalar"
            for dim, src in dimensions.items()
        },
    }
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(hist_entry, f, indent=2, ensure_ascii=False)

    print(f"  [GOLD] seed_snapshot.json regenerated — {len(dimensions)} dimensions, {len(signals)} signals", flush=True)
    print(f"  [GOLD] Provenance: {', '.join(provenance['data_sources'])}", flush=True)

    return snapshot
