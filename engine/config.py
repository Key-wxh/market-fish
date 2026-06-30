"""
MarketFish v5 — Centralized Configuration Loader.
Load chain: defaults.yaml → user_settings.yaml (optional, gitignored) → .env (secrets only).
Usage: from engine.config import get_config; cfg = get_config()
"""

import os
import yaml
import threading
from pathlib import Path
from copy import deepcopy

_CONFIG = None
_CONFIG_LOCK = threading.Lock()
_CONFIG_DIR = Path(__file__).parent.parent / "config"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Lists are replaced, not merged."""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_config(config_dir: str = None) -> dict:
    """
    Load configuration from YAML files.
    Chain: defaults.yaml → user_settings.yaml (optional) → env overrides.
    """
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    if config_dir is None:
        config_dir = _CONFIG_DIR
    else:
        config_dir = Path(config_dir)

    # 1. Load defaults
    defaults_path = config_dir / "defaults.yaml"
    if not defaults_path.exists():
        raise FileNotFoundError(f"Default config not found: {defaults_path}")

    with open(defaults_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 2. Override with user settings (if exists)
    user_path = config_dir / "user_settings.yaml"
    if user_path.exists():
        with open(user_path, encoding="utf-8") as f:
            user_config = yaml.safe_load(f)
            if user_config:
                config = _deep_merge(config, user_config)

    # 3. Apply env var overrides for specific keys
    _apply_env_overrides(config)

    _CONFIG = config
    return config


def _apply_env_overrides(config: dict):
    """Apply environment variable overrides for common settings."""
    # Seed
    if os.getenv("MARKETFISH_SEED"):
        try:
            config["simulation"]["random_seed"] = int(os.getenv("MARKETFISH_SEED"))
        except ValueError:
            pass

    # Rounds
    if os.getenv("MARKETFISH_ROUNDS"):
        try:
            config["pipeline"]["simulation_rounds"] = int(os.getenv("MARKETFISH_ROUNDS"))
            config["simulation"]["rounds"] = int(os.getenv("MARKETFISH_ROUNDS"))
        except ValueError:
            pass

    # Agent cap
    if os.getenv("MARKETFISH_AGENT_CAP"):
        try:
            config["pipeline"]["agent_consumer_cap"] = int(os.getenv("MARKETFISH_AGENT_CAP"))
        except ValueError:
            pass


def get_config() -> dict:
    """Get the loaded configuration (thread-safe singleton)."""
    global _CONFIG
    if _CONFIG is None:
        with _CONFIG_LOCK:
            if _CONFIG is None:
                load_config()
    return _CONFIG


def reload_config(config_dir: str = None):
    """Force reload configuration from disk."""
    global _CONFIG
    _CONFIG = None
    return load_config(config_dir)


# ── Convenience accessors ──

def _cfg_section(section: str) -> dict:
    return get_config().get(section, {})

def pipeline_cfg() -> dict:
    return _cfg_section("pipeline")

def simulation_cfg() -> dict:
    return _cfg_section("simulation")

def coupling_cfg() -> dict:
    return _cfg_section("coupling")

def rl_cfg() -> dict:
    return _cfg_section("rl")

def backtest_cfg() -> dict:
    return _cfg_section("backtest")

def network_cfg() -> dict:
    return _cfg_section("network")

def agent_gen_cfg() -> dict:
    return _cfg_section("agent_generation")

def report_cfg() -> dict:
    return _cfg_section("report")

def domain_cfg() -> dict:
    return _cfg_section("domain")

def calibration_cases() -> list:
    return get_config().get("calibration_cases", [])

def agent_batches() -> list:
    return get_config().get("agent_batches", [])
