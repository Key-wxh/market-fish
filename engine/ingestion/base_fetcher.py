"""
Base Fetcher — abstract class for all data source fetchers.
Every fetcher MUST implement: fetch() → validate() → save_bronze().
Data integrity rules enforced at the base class level.
"""
import json
import os
import gzip
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any


class BaseFetcher(ABC):
    """Abstract base for all data source fetchers.

    Lifecycle: fetch() → validate() → save_bronze()
    All raw data lands in bronze/{year}/{month}/{day}/{source}_{timestamp}.json
    NEVER overwrites. Append-only by timestamp.
    """

    def __init__(self, source_name: str, data_lake_root: str = None):
        self.source_name = source_name
        if data_lake_root is None:
            data_lake_root = str(Path(__file__).parent.parent.parent / "data_lake")
        self.data_lake_root = Path(data_lake_root)
        self.bronze_dir = self.data_lake_root / "bronze"

    # ── Abstract interface ──

    @abstractmethod
    def fetch(self) -> dict:
        """Call the API, return raw response as dict.

        Returns:
            {"status": "ok", "data": {...}, "metadata": {...}}
            or
            {"status": "error", "error": "message"}
        """
        ...

    @abstractmethod
    def validate(self, raw_data: dict) -> tuple[bool, list[str]]:
        """Validate raw API response.

        Returns:
            (is_valid: bool, warnings: list[str])
            is_valid=False means data is corrupted/unusable — do NOT save.
            warnings are advisory (e.g., "fewer results than expected").
        """
        ...

    # ── Bronze layer (raw storage) ──

    def save_bronze(self, result: dict) -> Optional[Path]:
        """Save raw API response to Bronze layer as timestamped JSON.

        Filename: {source}_{ISO8601}_{content_hash[:6]}.json
        Path: bronze/{YYYY}/{MM}/{DD}/

        Idempotent: if a file with the same content hash already exists today,
        skip duplicate write and return existing path.
        """
        if result.get("status") != "ok":
            print(f"  [BRONZE SKIP] {self.source_name}: fetch status={result.get('status')}", flush=True)
            return None

        # Generate content fingerprint for deduplication
        content_bytes = json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()[:8]

        now = datetime.now(timezone.utc)
        day_dir = self.bronze_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        day_dir.mkdir(parents=True, exist_ok=True)

        # Check for duplicate
        for existing in day_dir.glob(f"{self.source_name}_*_{content_hash}.json*"):
            print(f"  [BRONZE DUP] {self.source_name}: identical to {existing.name}", flush=True)
            return existing

        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        filename = f"{self.source_name}_{timestamp}_{content_hash}.json"
        filepath = day_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  [BRONZE] {self.source_name} → {filepath.name} ({len(content_bytes)} bytes)", flush=True)
        return filepath

    def compress_old_bronze(self, days: int = 30):
        """Compress Bronze files older than `days` to .json.gz."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        for json_file in self.bronze_dir.rglob("*.json"):
            if json_file.stat().st_mtime < cutoff:
                gz_path = json_file.with_suffix(".json.gz")
                if not gz_path.exists():
                    with open(json_file, "rb") as f_in:
                        with gzip.open(gz_path, "wb") as f_out:
                            f_out.write(f_in.read())
                    json_file.unlink()
                    print(f"  [BRONZE GZIP] {json_file.name} → {gz_path.name}", flush=True)

    # ── Full pipeline ──

    def run(self) -> dict:
        """Execute full fetch→validate→save cycle. Returns structured result."""
        try:
            raw = self.fetch()
            is_valid, warnings = self.validate(raw)
            result = {
                "source": self.source_name,
                "status": raw.get("status", "error"),
                "valid": is_valid,
                "warnings": warnings,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if is_valid:
                path = self.save_bronze(raw)
                result["bronze_path"] = str(path) if path else None
            else:
                result["bronze_path"] = None
                result["error"] = "Validation failed"
            return result
        except Exception as e:
            return {
                "source": self.source_name,
                "status": "error",
                "valid": False,
                "warnings": [],
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
