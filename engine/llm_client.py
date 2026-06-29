"""
8-layer JSON enforcement pipeline — MiroFish-verified.
Not "hope for JSON". FORCE JSON.
"""

import json
import re
import os
from openai import OpenAI
from json_repair import repair_json


class LLMClient:
    def __init__(self):
        self.deepseek = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com/v1",
        )
        # Qwen optional — only init if key is set
        qwen_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.qwen = None
        if qwen_key:
            self.qwen = OpenAI(
                api_key=qwen_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )

    def chat_json(
        self,
        system: str,
        user: str,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> dict:
        """8-layer pipeline: API → strip → extract → alias → wrap → repair → parse → validate"""
        if "deepseek" in model:
            client, model_id = self.deepseek, "deepseek-chat"
        elif self.qwen is not None:
            client, model_id = self.qwen, "qwen-plus"
        else:
            client, model_id = self.deepseek, "deepseek-chat"  # fallback to deepseek

        for attempt in range(max_retries):
            try:
                # Layer 1: API-level json_object mode
                resp = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content or ""

                # Layer 2: strip <think> tags (DeepSeek/豆包 artifact)
                raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)

                # Layer 3: strip markdown code fences
                raw = re.sub(r"```(?:json)?\s*", "", raw)
                raw = re.sub(r"```", "", raw)

                # Layer 4: bracket extraction — find first { or [
                match = re.search(r"[\{\[]", raw)
                if match:
                    raw = raw[match.start() :]

                # Layer 5: field alias mapping (LLM sometimes invents field names)
                # Handled downstream in each service

                # Layer 6: container wrapping — bare arrays → objects
                raw_stripped = raw.strip()
                if raw_stripped.startswith("["):
                    raw = '{"items":' + raw_stripped + "}"

                # Layer 7: json_repair — fix unclosed brackets, trailing commas
                try:
                    repaired = repair_json(raw)
                except Exception:
                    repaired = raw

                # Layer 8: parse + validate
                result = json.loads(repaired)
                return result

            except json.JSONDecodeError as e:
                if attempt == max_retries - 1:
                    raise ValueError(f"JSON parse failed after {max_retries} attempts: {e}")
                continue
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                continue

        raise RuntimeError("Unreachable")


# Singleton
_llm = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
