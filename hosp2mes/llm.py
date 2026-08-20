"""LLM client (DeepSeek-compatible) and a deterministic MockLLM.

When no API key is configured the agent runs in deterministic MockLLM mode so
that the whole system is reproducible and CI-friendly without network access.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx


@dataclass
class LLMMessage:
    role: str
    content: str


class MockLLM:
    """A stand-in for a real LLM.

    Instead of calling a remote model it echoes a structured decision back. It is
    used whenever ``AGENT_LLM_PROVIDER=mock`` (the default for CI / offline runs).
    The planner and decider still treat it as an opaque reasoner, so swapping in a
    real model requires no changes to the agent loop.
    """

    def complete(self, system: str, user: str) -> str:
        # Reserved for future structured prompting; for now the planner/decider
        # implement their own deterministic logic and only call this in LLM mode.
        return "{}"


class DeepSeekLLM:
    """OpenAI-compatible chat completion client (works with DeepSeek, etc.)."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = httpx.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def parse_json_block(text: str) -> dict:
        """Extract the first JSON object from an LLM response."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"no JSON found in LLM response: {text[:200]}")
        return json.loads(match.group(0))


def build_llm(config) -> "MockLLM | DeepSeekLLM":
    if config.use_real_llm():
        return DeepSeekLLM(config.llm_api_key, config.llm_base_url, config.llm_model)
    return MockLLM()
