"""
Scheduler — orchestrates the full ingestion cycle.
fetch_all → accumulate → aggregate → brief.
Designed to run as a cron job or PM2-managed process on HK server.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load .env for API tokens — PM2 runs python3 directly without shell sourcing
def _load_dotenv():
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass  # python-dotenv not installed, env vars must come from shell
_load_dotenv()


def _load_registry() -> dict:
    """Load dimension_registry.yaml (requires PyYAML)."""
    import yaml
    registry_path = Path(__file__).parent.parent.parent / "config" / "dimension_registry.yaml"
    with open(registry_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_enabled_fetchers(registry: dict) -> list[dict]:
    """Scan registry for all enabled sources. Returns list of source configs."""
    enabled = []
    for dim_name, dim_config in registry.get("dimensions", {}).items():
        for source in dim_config.get("sources", []):
            if source.get("enabled", False):
                source["_dimension"] = dim_name
                enabled.append(source)
    return enabled


def fetch_all(registry: dict = None, data_lake_root: str = None) -> list[dict]:
    """Run all enabled fetchers in parallel. Returns list of results."""
    if registry is None:
        registry = _load_registry()
    if data_lake_root is None:
        data_lake_root = str(Path(__file__).parent.parent.parent / "data_lake")

    sources = _get_enabled_fetchers(registry)
    if not sources:
        print("  [SCHEDULER] No enabled sources in registry. Enable some in dimension_registry.yaml.", flush=True)
        return []

    # Import active fetchers
    from engine.ingestion.fetchers import ACTIVE_FETCHERS

    results = []

    # Map source name → (fetcher_class, source_config)
    tasks = []
    for src in sources:
        name = src["name"]
        if name in ACTIVE_FETCHERS:
            tasks.append((name, ACTIVE_FETCHERS[name], src))
        else:
            results.append({
                "source": name,
                "status": "skipped",
                "error": f"Fetcher not implemented yet: {name}",
            })

    if not tasks:
        print("  [SCHEDULER] No fetchers available for enabled sources.", flush=True)
        return results

    # Parallel fetch
    print(f"  [SCHEDULER] Fetching {len(tasks)} sources in parallel...", flush=True)
    with ThreadPoolExecutor(max_workers=min(len(tasks), 4)) as executor:
        futures = {}

        for name, fetcher_cls, src_config in tasks:
            def _fetch(name=name, cls=fetcher_cls, cfg=src_config):
                try:
                    f = cls(data_lake_root=data_lake_root)
                    return f.run()
                except Exception as e:
                    return {
                        "source": name,
                        "status": "error",
                        "valid": False,
                        "error": str(e),
                    }

            futures[executor.submit(_fetch)] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result(timeout=120)  # 2 min timeout per source
                results.append(result)
                ok = "OK" if result.get("status") == "ok" else f"ERROR: {result.get('error', '?')}"
                print(f"  [SCHEDULER] {name}: {ok}", flush=True)
            except Exception as e:
                results.append({"source": name, "status": "error", "error": str(e)})
                print(f"  [SCHEDULER] {name}: TIMEOUT/ERROR — {e}", flush=True)

    return results


# Sources fetched on HK server and pushed to domestic bronze/
HK_SOURCES = ["github", "hackernews", "stackoverflow", "producthunt", "google_trends"]


def run_full_cycle(data_lake_root: str = None) -> dict:
    """Run the complete ingestion cycle: fetch → accumulate → aggregate → brief.

    This is the main entry point for both manual runs and cron/PM2 scheduling.
    """
    t0 = time.time()

    try:
        registry = _load_registry()
    except Exception as e:
        return {"status": "error", "stage": "load_registry", "error": str(e)}

    if data_lake_root is None:
        data_lake_root = str(Path(__file__).parent.parent.parent / "data_lake")

    print(f"\n{'='*60}")
    print(f"  MarketFish Ingestion Cycle")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}", flush=True)

    # 1. Fetch all (domestic sources only — HK sources pushed by HK cron)
    fetch_results = fetch_all(registry, data_lake_root)
    ok = sum(1 for r in fetch_results if r.get("status") == "ok")
    fail = sum(1 for r in fetch_results if r.get("status") != "ok")
    print(f"\n  [CYCLE] Fetch: {ok} ok, {fail} failed, {len(fetch_results)} total", flush=True)

    # 2. Accumulate (Bronze → Silver) — domestic sources + HK-pushed sources
    from engine.ingestion.accumulator import accumulate_bronze_to_silver
    acc_results = []
    acc_sources = [s["name"] for s in _get_enabled_fetchers(registry)]
    # HK sources: fetched on HK server, pushed to domestic bronze — accumulate here
    for hk_src in HK_SOURCES:
        if hk_src not in acc_sources:
            acc_sources.append(hk_src)
    for name in acc_sources:
        result = accumulate_bronze_to_silver(name, data_lake_root)
        if result.get("rows_added", 0) > 0:
            acc_results.append(result)
    print(f"  [CYCLE] Accumulate: {len(acc_results)} sources had new data", flush=True)

    # 3. Aggregate (Silver → Gold)
    from engine.ingestion.aggregator import regenerate_gold
    snapshot = regenerate_gold(data_lake_root)

    # 4. Generate daily brief
    from engine.ingestion.daily_brief import generate_daily_brief
    brief = generate_daily_brief(data_lake_root)

    elapsed = time.time() - t0
    print(f"\n  [CYCLE] Complete in {elapsed:.1f}s — {len(snapshot.get('dimensions', {}))} dimensions, "
          f"{len(snapshot.get('signals', {}))} signals", flush=True)

    return {
        "status": "ok",
        "elapsed_seconds": round(elapsed, 1),
        "fetch": {"ok": ok, "failed": fail, "total": len(fetch_results)},
        "accumulate": {"sources_updated": len(acc_results)},
        "gold": {
            "dimensions": len(snapshot.get("dimensions", {})),
            "signals": len(snapshot.get("signals", {})),
            "snapshot_id": snapshot.get("snapshot_id"),
        },
        "brief_length": len(brief),
    }


def server_loop(data_lake_root: str = None, interval_minutes: int = 60):
    """Continuous server mode — run cycle every N minutes. For PM2 deployment."""
    print(f"  [SERVER] MarketFish Ingestion Server starting (interval={interval_minutes}min)", flush=True)
    print(f"  [SERVER] PM2-managed. Logs to data_lake/ingestion.log", flush=True)

    while True:
        try:
            result = run_full_cycle(data_lake_root)
            status = result.get("status", "error")
            print(f"  [SERVER] Cycle complete: {status}. Next in {interval_minutes}min.", flush=True)
        except Exception as e:
            print(f"  [SERVER] Cycle error: {e}. Retrying in {interval_minutes}min.", flush=True)

        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MarketFish Data Ingestion Scheduler")
    parser.add_argument("--once", action="store_true", help="Run one full cycle and exit")
    parser.add_argument("--server", action="store_true", help="Run continuously (PM2 mode)")
    parser.add_argument("--interval", type=int, default=360, help="Minutes between cycles (server mode, default 6h)")
    parser.add_argument("--data-lake", type=str, default=None, help="Path to data_lake/")

    args = parser.parse_args()

    if args.once:
        result = run_full_cycle(args.data_lake)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.server:
        server_loop(args.data_lake, args.interval)
    else:
        parser.print_help()
