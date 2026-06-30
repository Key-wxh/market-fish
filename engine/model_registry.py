"""
Model Registry — capability-based LLM selection.
Loads models from config/models_registry.json.
Agent types bind to capabilities, not model names.
Supports OpenAI-compatible, Anthropic Messages, and Google Gemini APIs.
"""

import json
import os
import threading
from pathlib import Path
from openai import OpenAI


class ModelRegistry:
    """Manages LLM provider/models registry with capability-based resolution."""

    def __init__(self, registry_path: str = None):
        if registry_path is None:
            registry_path = Path(__file__).parent.parent / "config" / "models_registry.json"
        self.registry_path = str(registry_path)
        self.data = self._load()
        self.clients = {}  # Lazy-init clients

    def _load(self) -> dict:
        with open(self.registry_path, encoding="utf-8") as f:
            return json.load(f)

    def reload(self):
        """Reload registry from disk (after user edits JSON)."""
        self.data = self._load()
        self.clients = {}

    # ── Provider queries ──

    def list_providers(self) -> list:
        return list(self.data.get("providers", {}).keys())

    def get_provider(self, name: str) -> dict:
        return self.data.get("providers", {}).get(name, {})

    # ── Model queries ──

    def list_active_models(self, provider: str = None) -> list:
        """List all active models, optionally filtered by provider."""
        models = []
        providers = self.data.get("providers", {})
        for pname, pinfo in providers.items():
            if provider and pname != provider:
                continue
            for m in pinfo.get("models", []):
                if m.get("status") == "active":
                    models.append({"provider": pname, **m})
        return models

    def get_active_model(self, provider: str) -> dict:
        """Get the first active model for a provider."""
        pinfo = self.get_provider(provider)
        for m in pinfo.get("models", []):
            if m.get("status") == "active":
                return m
        return None

    # ── Capability matching ──

    def _score_model(self, model_caps: list, required: list, prefer: str) -> float:
        """Score a model against capability requirements. Higher = better match."""
        if not required:
            return 0.5
        required_set = set(required)
        caps_set = set(model_caps)
        # Must have all required capabilities
        if not required_set.issubset(caps_set):
            return -1.0  # Disqualified
        # Base score: fraction of required caps matched
        score = len(required_set & caps_set) / len(required_set)
        # Bonus for preferred capability
        if prefer and prefer in caps_set:
            score += 0.3
        # Bonus for extra capabilities
        extra = caps_set - required_set
        score += len(extra) * 0.05
        return score

    def resolve(self, agent_type: str) -> tuple:
        """
        Resolve the best model for an agent type.
        Returns (provider_name, model_name, client).
        Auto-fallbacks if best match is unavailable.
        """
        assignment = self.data.get("assignments", {}).get(agent_type)
        if not assignment:
            assignment = self.data.get("assignments", {}).get("default", {"requires": ["json"], "prefer": "cheap"})

        required = assignment.get("requires", ["json"])
        prefer = assignment.get("prefer", "cheap")

        # Score all active models
        scored = []
        for pname, pinfo in self.data.get("providers", {}).items():
            # Check API key is set
            env_key = pinfo.get("env_key", "")
            if env_key and not os.getenv(env_key):
                continue
            # Check provider type is supported
            api_type = pinfo.get("api_type", "openai_compatible")
            for m in pinfo.get("models", []):
                if m.get("status") != "active":
                    continue
                s = self._score_model(m.get("capabilities", []), required, prefer)
                if s >= 0:
                    scored.append((s, pname, m["name"], api_type, pinfo))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Try best match first, fall through
        fallback_chain = self.data.get("fallback_chain", [])
        tried = set()

        for _, pname, mname, api_type, pinfo in scored:
            if pname not in tried:
                tried.add(pname)
                client = self._get_client(pname, pinfo, api_type)
                if client:
                    return (pname, mname, client)

        # Fallback chain as last resort
        for pname in fallback_chain:
            if pname in tried:
                continue
            pinfo = self.get_provider(pname)
            if not pinfo:
                continue
            env_key = pinfo.get("env_key", "")
            if env_key and not os.getenv(env_key):
                continue
            model = self.get_active_model(pname)
            if model:
                api_type = pinfo.get("api_type", "openai_compatible")
                client = self._get_client(pname, pinfo, api_type)
                if client:
                    return (pname, model["name"], client)

        raise RuntimeError(f"No available model for agent_type='{agent_type}'. Check API keys and model registry.")

    # ── Client management ──

    def _get_client(self, provider_name: str, pinfo: dict, api_type: str):
        """Get or create a client for a provider."""
        if provider_name in self.clients:
            return self.clients[provider_name]

        api_key = os.getenv(pinfo.get("env_key", ""))
        if not api_key:
            return None

        timeout = pinfo.get("timeout", 180.0)
        max_retries = pinfo.get("max_retries", 1)

        try:
            if api_type == "openai_compatible":
                client = OpenAI(
                    api_key=api_key,
                    base_url=pinfo.get("base_url", ""),
                    timeout=timeout,
                    max_retries=max_retries,
                )
            elif api_type == "anthropic_messages":
                # Anthropic uses the same OpenAI-compatible base (with /v1/messages)
                # Their Messages API is accessible via the same base_url pattern
                client = OpenAI(
                    api_key=api_key,
                    base_url=pinfo.get("base_url", "https://api.anthropic.com/v1"),
                    timeout=timeout,
                    max_retries=max_retries,
                )
            elif api_type == "google_gemini":
                # Google Gemini has a different API structure
                # We create an OpenAI-compatible wrapper for now
                client = OpenAI(
                    api_key=api_key,
                    base_url=pinfo.get("base_url", ""),
                    timeout=timeout,
                    max_retries=max_retries,
                )
            else:
                client = OpenAI(
                    api_key=api_key,
                    base_url=pinfo.get("base_url", ""),
                    timeout=timeout,
                    max_retries=max_retries,
                )

            self.clients[provider_name] = client
            return client
        except Exception as e:
            print(f"  [REGISTRY] Failed to create client for {provider_name}: {e}", flush=True)
            return None

    def prefetch_all(self):
        """Pre-initialize clients for all configured providers."""
        for pname, pinfo in self.data.get("providers", {}).items():
            api_type = pinfo.get("api_type", "openai_compatible")
            self._get_client(pname, pinfo, api_type)

    def status_report(self) -> dict:
        """Return a status report of all providers and models."""
        report = {}
        for pname, pinfo in self.data.get("providers", {}).items():
            env_key = pinfo.get("env_key", "")
            has_key = bool(os.getenv(env_key))
            active_models = [m["name"] for m in pinfo.get("models", []) if m.get("status") == "active"]
            report[pname] = {
                "api_type": pinfo.get("api_type"),
                "key_configured": has_key,
                "client_ready": pname in self.clients,
                "active_models": active_models,
            }
        return report


# Thread-safe singleton
_registry = None
_registry_lock = threading.Lock()


def get_registry(registry_path: str = None) -> ModelRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ModelRegistry(registry_path)
    return _registry
