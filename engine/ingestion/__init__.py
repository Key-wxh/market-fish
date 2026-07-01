"""
MarketFish Data Ingestion — Bronze → Silver → Gold pipeline.
Data is never overwritten. Every fetch is timestamped and append-only.
Trust = provenance. Every signal cites its validating paper.
"""

from engine.ingestion.base_fetcher import BaseFetcher
from engine.ingestion.seed_injector import inject_seed_data
from engine.ingestion.accumulator import accumulate_bronze_to_silver
from engine.ingestion.aggregator import regenerate_gold
from engine.ingestion.daily_brief import generate_daily_brief
