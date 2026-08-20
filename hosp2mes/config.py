"""Runtime configuration for the Hosp2MES agent (env / .env driven)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    backend_base_url: str = "http://localhost:8000"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "deepseek-chat"
    agent_mode: str = "hosp2mes"  # "hosp2mes" | "baseline"
    llm_provider: str = "mock"    # "mock" | "deepseek"
    publish_url: str = ""         # optional backend URL to stream traces to
    max_steps: int = 100

    @classmethod
    def load(cls) -> "Config":
        return cls(
            backend_base_url=os.getenv("BACKEND_BASE_URL", "http://localhost:8000"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
            agent_mode=os.getenv("AGENT_MODE", "hosp2mes"),
            llm_provider=os.getenv("AGENT_LLM_PROVIDER", "mock"),
            publish_url=os.getenv("AGENT_PUBLISH_URL", ""),
            max_steps=int(os.getenv("AGENT_MAX_STEPS", "100")),
        )

    def use_real_llm(self) -> bool:
        return self.llm_provider == "deepseek" and bool(self.llm_api_key)
