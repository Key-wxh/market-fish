"""
Multi-LLM Client — Heterogeneous Agent Architecture.
Uses ModelRegistry for capability-based model selection.
Agent types bind to capabilities, not model names.

Machine Spirits 2026 principle: heterogeneous agents > homogeneous.
Agent Bazaar 2026 principle: economic alignment requires diverse cognition.
"""

import json
import re
import os
import time
import threading
from dotenv import load_dotenv
load_dotenv()
from json_repair import repair_json
from engine.model_registry import get_registry


class MultiLLMClient:
    """Multi-model client with 8-layer JSON enforcement + capability-based model selection."""

    def __init__(self):
        self.registry = get_registry()
        self.clients = {}  # provider_name -> OpenAI client (lazy)

        # Print status
        status = self.registry.status_report()
        active = sum(1 for s in status.values() if s["key_configured"])
        total = len(status)
        print(f"MultiLLMClient: {active}/{total} providers configured via registry")
        for name, s in status.items():
            if s["key_configured"]:
                models = ", ".join(s["active_models"])
                print(f"  - {name}: {models} ({s['api_type']})")

        if active == 0:
            raise RuntimeError("No LLM API keys configured. Check .env file and models_registry.json.")

    def _resolve(self, agent_type: str) -> tuple:
        """Resolve (provider_name, model_name, client) for an agent type."""
        provider, model_name, client = self.registry.resolve(agent_type)
        self.clients[provider] = client
        return provider, model_name, client

    def chat_json(
        self,
        system: str,
        user: str,
        agent_type: str = "default",
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> dict:
        """8-layer JSON pipeline with capability-based model selection + auto fallback."""
        provider, model_name, client = self._resolve(agent_type)

        for attempt in range(max_retries):
            try:
                # Layer 1: API-level json_object
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content or ""

                # Layer 2: strip <think> tags (DeepSeek-specific, harmless for others)
                raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)

                # Layer 3: strip markdown fences
                raw = re.sub(r"```(?:json)?\s*", "", raw)
                raw = re.sub(r"```", "", raw)

                # Layer 4: bracket extraction
                match = re.search(r"[\{\[]", raw)
                if match:
                    raw = raw[match.start():]

                # Layer 5: alias mapping (handled downstream)

                # Layer 6: container wrapping
                raw_stripped = raw.strip()
                if raw_stripped.startswith("["):
                    raw = '{"items":' + raw_stripped + "}"

                # Layer 7: json_repair
                try:
                    repaired = repair_json(raw)
                except Exception:
                    repaired = raw

                # Layer 8: parse
                result = json.loads(repaired)
                return result

            except json.JSONDecodeError:
                if attempt == max_retries - 1:
                    raise
                time.sleep(0.5)
                continue
            except Exception as e:
                err_str = str(e)
                # Auth failure → invalidate provider in both caches and retry with next
                if "401" in err_str or "Invalid Authentication" in err_str or "auth" in err_str.lower():
                    print(f"  [AUTH_FAIL] {provider} key invalid — invalidating from pool", flush=True)
                    self.registry.invalidate_client(provider)
                    if provider in self.clients:
                        del self.clients[provider]
                    try:
                        provider, model_name, client = self._resolve(agent_type)
                    except RuntimeError:
                        raise RuntimeError(f"All models exhausted after auth failure on {provider}")
                    continue
                if attempt == max_retries - 1:
                    raise
                time.sleep(1.0)
                continue

        raise RuntimeError("Unreachable")

    def chat_text(
        self,
        system: str,
        user: str,
        agent_type: str = "default",
        temperature: float = 0.9,
        max_tokens: int = 1000,
    ) -> str:
        """Natural language chat (no JSON enforcement). Used for Agent Dialogue."""
        provider, model_name, client = self._resolve(agent_type)

        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            raw = resp.choices[0].message.content or ""
            # Strip think tags only, keep natural text
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
            return raw.strip()
        except Exception as e:
            return f"[Agent unavailable: {e}]"


# Thread-safe singleton
_multi_llm = None
_multi_llm_lock = threading.Lock()


def get_llm() -> MultiLLMClient:
    global _multi_llm
    if _multi_llm is None:
        with _multi_llm_lock:
            if _multi_llm is None:
                _multi_llm = MultiLLMClient()
    return _multi_llm
