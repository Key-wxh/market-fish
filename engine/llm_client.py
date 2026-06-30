"""
Multi-LLM Client — Heterogeneous Agent Architecture.
7 models from GEO易 production config + Machine Spirits principle:
  - Different agent types use different LLMs (异质 > 同质)
  - Stronger models on competitive/strategic decisions
  - Faster/cheaper models on routine consumer decisions

Model assignments (Machine Spirits 2026 + Agent Bazaar 2026):
  Consumer B2C → DeepSeek V4 Pro (balanced, fast)
  SMB → Qwen3 Max (pragmatic, cost-aware)
  Enterprise → Kimi K2.5 (long-context, strategic)
  Competitor → DeepSeek V4 Pro + high temp (creative/adaptive)
  Environment → Mixed rotation (diverse perspectives)
  Reporter Student → Doubao Seed 1.6 (analytical)
  Reporter Teacher → Zhipu GLM-4 (critical/skeptical)
"""

import json
import re
import os
import time
from openai import OpenAI
from json_repair import repair_json


class MultiLLMClient:
    """7-model client with 8-layer JSON enforcement. Heterogeneous assignment per agent type."""

    # Model registry — from GEO易 production + latest versions
    MODELS = {
        "deepseek": {
            "key": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",  # Latest: April 2026, 1.6T MoE
            "trait": "balanced, fast, JSON-reliable",
        },
        "qwen": {
            "key": "QIANWEN_API_KEY",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen3-max",  # Latest flagship
            "trait": "pragmatic, cost-aware, good at business logic",
        },
        # Kimi excluded — API rate limited. Enterprise/Graph reassigned to Baidu/Qwen.
        "doubao": {
            "key": "DOUBAO_API_KEY",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "model": "doubao-seed-1-6-251015",  # Reasoning model w/ search
            "trait": "analytical, search-capable, detail-oriented",
        },
        "zhipu": {
            "key": "ZHIPU_API_KEY",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4",
            "trait": "skeptical, critical thinking",
        },
        "baidu": {
            "key": "BAIDU_API_KEY",
            "base_url": "https://qianfan.baidubce.com/v2",
            "model": "ernie-4.0-turbo-128k",
            "trait": "broad knowledge, enterprise-ready",
        },
        "hunyuan": {
            "key": "HUNYUAN_API_KEY",
            "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
            "model": "hunyuan-pro",
            "trait": "well-rounded, Tencent ecosystem aware",
        },
    }

    # Heterogeneous assignment (Machine Spirits principle)
    AGENT_MODEL_MAP = {
        "consumer": "deepseek",     # Balanced, fast JSON
        "smb": "qwen",              # Pragmatic, cost-aware
        "enterprise": "baidu",      # Broad knowledge, enterprise-ready (was Kimi, rate-limited)
        "competitor": "deepseek",   # Creative adaptation
        "environment": "baidu",     # Broad knowledge
        "reporter_student": "doubao",  # Analytical
        "reporter_teacher": "zhipu",   # Skeptical/critical
        "ontology": "deepseek",     # Core analysis
        "graph": "qwen",            # Relationship extraction (was Kimi, rate-limited)
        "idea": "deepseek",         # Creative generation
        "default": "deepseek",
    }

    def __init__(self):
        self.clients = {}
        for name, cfg in self.MODELS.items():
            key = os.getenv(cfg["key"], "")
            if key:
                self.clients[name] = OpenAI(api_key=key, base_url=cfg["base_url"])
            else:
                print(f"  [WARN] {name} ({cfg['model']}) not configured — will skip")

        if not self.clients:
            raise RuntimeError("No LLM API keys configured. Check .env file.")

        print(f"MultiLLMClient: {len(self.clients)}/{len(self.MODELS)} models ready")
        for name in self.clients:
            print(f"  - {name}: {self.MODELS[name]['model']} ({self.MODELS[name]['trait']})")

    def _resolve_model(self, agent_type: str) -> str:
        """Resolve model name with fallback. If assigned model is unavailable, use deepseek."""
        primary = self.AGENT_MODEL_MAP.get(agent_type, "default")
        if primary in self.clients:
            return primary
        # Fallback chain
        for fallback in ["deepseek", "qwen", "doubao", "baidu", "hunyuan", "zhipu", "kimi"]:
            if fallback in self.clients:
                return fallback
        return list(self.clients.keys())[0]

    def chat_json(
        self,
        system: str,
        user: str,
        agent_type: str = "default",
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> dict:
        """8-layer JSON pipeline with heterogeneous model selection + automatic fallback."""
        model_name = self._resolve_model(agent_type)
        client = self.clients[model_name]
        cfg = self.MODELS[model_name]

        for attempt in range(max_retries):
            try:
                # Layer 1: API-level json_object
                resp = client.chat.completions.create(
                    model=cfg["model"],
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content or ""

                # Layer 2: strip <think> tags
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

            except Exception as e:
                err_str = str(e)
                # If auth failure, mark model as unavailable and fallback
                if "401" in err_str or "Invalid Authentication" in err_str or "auth" in err_str.lower():
                    if model_name in self.clients:
                        print(f"  [AUTH_FAIL] {model_name} key invalid — removing from pool")
                        del self.clients[model_name]
                    # Retry with fallback model
                    model_name = self._resolve_model(agent_type)
                    if model_name not in self.clients:
                        raise RuntimeError(f"All models exhausted after auth failure on {model_name}")
                    client = self.clients[model_name]
                    cfg = self.MODELS[model_name]
                    continue
                if attempt == max_retries - 1:
                    raise
                time.sleep(1.0)
                continue

            except json.JSONDecodeError:
                if attempt == max_retries - 1:
                    raise
                time.sleep(0.5)
                continue
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1.0)
                continue

        raise RuntimeError("Unreachable")


# Singleton
_multi_llm = None


def get_llm() -> MultiLLMClient:
    global _multi_llm
    if _multi_llm is None:
        _multi_llm = MultiLLMClient()
    return _multi_llm
