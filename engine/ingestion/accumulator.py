"""
Accumulator — Bronze → Silver transformation.
Reads raw Bronze JSON files, cleans/normalizes, appends to Silver Parquet time-series.
Each source has its own Parquet file. Time-series append-only, never overwrite.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _ensure_silver_dir(data_lake_root: str) -> Path:
    silver = Path(data_lake_root) / "silver" / "time_series"
    silver.mkdir(parents=True, exist_ok=True)
    return silver


def _read_bronze_files_since(source_name: str, bronze_dir: Path, since_iso: Optional[str] = None) -> list[dict]:
    """Scan bronze/ for all fetch results of source_name since the given timestamp.
    Returns list of (fetch_timestamp, data_dict) sorted by time."""
    results = []
    if not bronze_dir.exists():
        return results

    for json_file in sorted(bronze_dir.rglob(f"{source_name}_*.json")):
        # Parse timestamp from filename: source_YYYYMMDDTHHMMSSZ_hash.json
        fname = json_file.stem
        parts = fname.split("_")
        if len(parts) < 2:
            continue
        ts_str = parts[1]  # YYYYMMDDTHHMMSSZ
        try:
            file_ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").isoformat()
        except ValueError:
            file_ts = "unknown"

        if since_iso and file_ts <= since_iso:
            continue

        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
                results.append({"timestamp": file_ts, "data": data, "file": str(json_file)})
        except Exception:
            continue

    return results


def accumulate_bronze_to_silver(source_name: str, data_lake_root: str = None,
                                since: Optional[str] = None) -> dict:
    """Read all new Bronze files for source_name, write accumulated rows to Silver Parquet.

    Since Parquet requires pandas/pyarrow, which may not be installed in all environments,
    this function also supports JSON-based time-series accumulation as a fallback.

    Returns:
        {"status": "ok", "rows_added": N, "parquet_path": "..."}
        or
        {"status": "json_fallback", "rows_added": N, "json_path": "..."}
    """
    if data_lake_root is None:
        data_lake_root = str(Path(__file__).parent.parent.parent / "data_lake")

    bronze_dir = Path(data_lake_root) / "bronze"
    silver_dir = _ensure_silver_dir(data_lake_root)

    # Read new bronze files
    bronze_entries = _read_bronze_files_since(source_name, bronze_dir, since)
    if not bronze_entries:
        return {"status": "ok", "rows_added": 0, "message": "No new bronze files"}

    # Extract time-series rows from bronze data
    rows = _extract_time_series(source_name, bronze_entries)
    if not rows:
        return {"status": "ok", "rows_added": 0, "message": "No time-series data extracted"}

    # Try Parquet first, fall back to JSON
    try:
        import pandas as pd
        parquet_path = silver_dir / f"{source_name}.parquet"
        new_df = pd.DataFrame(rows)
        new_df["_accumulated_at"] = datetime.now(timezone.utc).isoformat()

        if parquet_path.exists():
            existing = pd.read_parquet(parquet_path)
            # Upsert: remove old rows with same timestamps, append new
            existing = existing[~existing["date"].isin(new_df["date"])]
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined = combined.sort_values("date").drop_duplicates(subset=["date"], keep="last")
            combined.to_parquet(parquet_path, index=False)
        else:
            new_df.to_parquet(parquet_path, index=False)

        return {
            "status": "ok",
            "source": source_name,
            "rows_added": len(rows),
            "total_rows": len(pd.read_parquet(parquet_path)),
            "parquet_path": str(parquet_path),
        }
    except ImportError:
        # Fallback: accumulate as JSON time-series
        json_path = silver_dir / f"{source_name}_ts.json"
        existing_rows = []
        if json_path.exists():
            with open(json_path, encoding="utf-8") as f:
                existing_rows = json.load(f)

        # Upsert by date
        date_index = {r["date"]: i for i, r in enumerate(existing_rows)}
        for row in rows:
            if row["date"] in date_index:
                existing_rows[date_index[row["date"]]] = row
            else:
                existing_rows.append(row)

        existing_rows.sort(key=lambda r: r["date"])
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(existing_rows, f, indent=2, ensure_ascii=False)

        return {
            "status": "json_fallback",
            "source": source_name,
            "rows_added": len(rows),
            "total_rows": len(existing_rows),
            "json_path": str(json_path),
        }


def _extract_time_series(source_name: str, bronze_entries: list[dict]) -> list[dict]:
    """Extract time-series rows from bronze entries.
    Each source has its own extraction logic."""
    rows = []

    for entry in bronze_entries:
        data = entry.get("data", {}).get("data", {})
        ts = entry["timestamp"]

        if source_name == "fred":
            # Now World Bank format: countries → indicators → latest/previous
            countries = data.get("countries", {})
            summary = data.get("summary", {})
            if not summary:
                continue
            row = {"date": ts[:10]}
            for key, val in summary.items():
                row[key] = val
            row["datapoints_fetched"] = data.get("datapoints_fetched", 0)
            rows.append(row)

        elif source_name == "github":
            row = {
                "date": ts[:10],
                "total_repos": data.get("total_repos", 0),
                "total_stars": data.get("total_stars", 0),
                "ai_ml_repos": data.get("ai_ml_count", 0),
                "hot_topics": json.dumps(data.get("hot_topics", [])),
                "language_distribution": json.dumps(data.get("language_distribution", [])),
            }
            rows.append(row)

        elif source_name == "hackernews":
            row = {
                "date": ts[:10],
                "stories_fetched": data.get("stories_fetched", 0),
                "total_score": data.get("total_score", 0),
                "total_comments": data.get("total_comments", 0),
                "ai_stories": data.get("ai_stories", 0),
                "ai_story_ratio": data.get("ai_story_ratio", 0),
                "sentiment_score": data.get("sentiment_score", 0),
                "hot_topics": json.dumps(data.get("hot_topics", [])),
                "avg_story_score": data.get("avg_story_score", 0),
            }
            rows.append(row)

        elif source_name == "stackoverflow":
            row = {
                "date": ts[:10],
                "total_weekly_questions": data.get("total_weekly_questions", 0),
                "ai_related_questions": data.get("ai_related_questions", 0),
                "ai_question_ratio": data.get("ai_question_ratio", 0),
                "top_tags": json.dumps(data.get("tags", [])[:10]),
            }
            rows.append(row)

        elif source_name == "eastmoney":
            row = {
                "date": ts[:10],
                "total_industries": data.get("total_industries", 0),
                "active_industries": data.get("active_industries", 0),
                "total_bottlenecks": data.get("total_bottlenecks", 0),
                "benchmark_latest_close": data.get("benchmark_latest_close"),
                "benchmark_latest_change_pct": data.get("benchmark_latest_change_pct"),
                "recent_20d_up_ratio": data.get("recent_20d_up_ratio", 0),
                "cpi_yoy_pct": data.get("cpi_yoy_pct"),
                "cpi_date": data.get("cpi_date"),
                "kline_count": data.get("kline_count", 0),
            }
            rows.append(row)

        elif source_name == "producthunt":
            row = {
                "date": ts[:10],
                "total_launches": data.get("total_launches", 0),
                "total_votes": data.get("total_votes", 0),
                "avg_votes": data.get("avg_votes", 0),
                "ai_launches": data.get("ai_launches", 0),
                "ai_ratio": data.get("ai_ratio", 0),
                "hot_topics": json.dumps(data.get("hot_topics", [])),
            }
            rows.append(row)

        elif source_name == "36kr":
            row = {
                "date": ts[:10],
                "total_articles": data.get("total_articles", 0),
                "ai_ratio": data.get("ai_ratio", 0),
                "funding_ratio": data.get("funding_ratio", 0),
                "category_counts": json.dumps(data.get("category_counts", {})),
            }
            rows.append(row)

        elif source_name == "google_trends":
            row = {
                "date": ts[:10],
                "categories_tracked": data.get("categories_tracked", 0),
                "overall_interest_index": data.get("overall_interest_index", 0),
                "ai_interest_index": data.get("ai_interest_index", 0),
            }
            rows.append(row)

    return rows


def validate_silver_integrity(data_lake_root: str = None) -> dict:
    """Check all Silver Parquet/JSON files for data integrity.
    Returns health report for each source."""
    if data_lake_root is None:
        data_lake_root = str(Path(__file__).parent.parent.parent / "data_lake")

    silver_dir = Path(data_lake_root) / "silver" / "time_series"
    if not silver_dir.exists():
        return {"status": "ok", "sources": {}, "message": "No silver data yet"}

    report = {}
    for f in sorted(silver_dir.glob("*")):
        source = f.stem.replace("_ts", "")
        try:
            if f.suffix == ".parquet":
                import pandas as pd
                df = pd.read_parquet(f)
                report[source] = {
                    "format": "parquet",
                    "rows": len(df),
                    "columns": list(df.columns),
                    "date_range": f"{df['date'].min()} → {df['date'].max()}" if "date" in df.columns else "N/A",
                    "size_kb": round(f.stat().st_size / 1024, 1),
                }
            elif f.suffix == ".json":
                with open(f, encoding="utf-8") as fh:
                    rows = json.load(fh)
                    dates = [r.get("date", "") for r in rows]
                    report[source] = {
                        "format": "json",
                        "rows": len(rows),
                        "date_range": f"{min(dates)} → {max(dates)}" if dates else "N/A",
                        "size_kb": round(f.stat().st_size / 1024, 1),
                    }
        except Exception as e:
            report[source] = {"error": str(e)}

    return {"status": "ok", "sources": report}
