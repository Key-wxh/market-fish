"""
Seed Injector — bridges Gold snapshot to the pipeline.
Replaces the old hardcoded 3-source prompt in ontology_generator with
source-agnostic iteration over all available dimensions.
"""
import json
from pathlib import Path
from typing import Optional


def load_snapshot(snapshot_path: str = None, data_lake_root: str = None) -> dict:
    """Load a gold seed snapshot from disk.

    Args:
        snapshot_path: Direct path to a specific snapshot JSON.
        data_lake_root: Fallback — loads latest gold/seed_snapshot.json.

    Returns:
        The full snapshot dict with dimensions, signals, provenance.
    """
    if snapshot_path:
        path = Path(snapshot_path)
    else:
        if data_lake_root is None:
            data_lake_root = str(Path(__file__).parent.parent.parent / "data_lake")
        path = Path(data_lake_root) / "gold" / "seed_snapshot.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Gold snapshot not found at {path}. "
            f"Run 'python -m engine.ingestion.scheduler --once' to generate one."
        )

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def inject_seed_data(snapshot: dict, target_dimensions: Optional[list[str]] = None) -> str:
    """Convert a gold snapshot into an LLM-ready prompt fragment for ontology generation.

    Source-agnostic: iterates over ALL available dimensions rather than
    hardcoding freelancer/economy/tech.

    Args:
        snapshot: The full gold snapshot dict (from load_snapshot or aggregator).
        target_dimensions: Optional whitelist of dimension keys to include.
                          If None, includes all dimensions with data.

    Returns:
        A multi-paragraph prompt string ready to inject into the ontology generator.
    """
    dimensions = snapshot.get("dimensions", {})
    signals = snapshot.get("signals", {})
    prov = snapshot.get("provenance", {})

    if target_dimensions is None:
        target_dimensions = [k for k, v in dimensions.items() if v]

    prompt_parts = []

    for dim_name in target_dimensions:
        dim_data = dimensions.get(dim_name)
        if not dim_data:
            continue

        # Human-readable dimension label
        dim_label = dim_name.replace("_", " ").title()
        prompt_parts.append(
            f"{dim_label}:\n{json.dumps(dim_data, indent=2, ensure_ascii=False)}"
        )

    # Active signals with interpretation
    if signals:
        active = [name for name, active in signals.items() if active]
        if active:
            signal_lines = ["\nACTIVE MARKET SIGNALS:"]
            for s in sorted(active):
                signal_lines.append(f"  - {s}")
            prompt_parts.append("\n".join(signal_lines))

    # Provenance for transparency
    if prov:
        sources = prov.get("data_sources", [])
        oldest = prov.get("oldest_data_point", "?")
        newest = prov.get("newest_data_point", "?")
        prompt_parts.append(
            f"\nDATA PROVENANCE: Sources={', '.join(sources) if sources else 'N/A'}. "
            f"Collection period: {oldest} to {newest}."
        )

    return "\n\n".join(prompt_parts)


def snapshot_to_legacy_seed(snapshot: dict) -> dict:
    """Convert a gold snapshot to the legacy seed_data dict format
    that pipeline.py currently expects.

    This is a compatibility bridge — the pipeline still calls
    seed_data.get('freelancer'), seed_data.get('economy'), etc.
    This maps the new dimension structure back to those old keys.

    Returns:
        A dict with old-style keys (freelancer, economy, tech, consumer, b2b)
        populated from the snapshot dimensions.
    """
    dims = snapshot.get("dimensions", {})

    legacy = {}

    # Map: gold dimension → legacy seed key
    mapping = {
        "freelance_demand": "freelancer",
        "macroeconomic": "economy",
        "technology_adoption": "tech",
        "consumer_behavior": "consumer",
        "b2b_software": "b2b",
    }

    for dim_name, legacy_key in mapping.items():
        if dim_name in dims:
            legacy[legacy_key] = dims[dim_name]
        else:
            legacy[legacy_key] = {}

    # Also pass the full dimensions dict and signals
    legacy["_dimensions"] = dims
    legacy["_signals"] = snapshot.get("signals", {})
    legacy["_provenance"] = snapshot.get("provenance", {})
    legacy["_snapshot_id"] = snapshot.get("snapshot_id", "unknown")

    return legacy
