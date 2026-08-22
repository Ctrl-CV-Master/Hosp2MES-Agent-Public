"""Runtime configuration for the Hosp2MES agent (env / .env driven)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _load_dotenv() -> None:
    """Load ``.env`` into ``os.environ`` without overriding existing values.

    Used so a real DeepSeek-compatible API key can live in a local, git-ignored
    ``.env`` and never be committed. ``python-dotenv`` is preferred when
    installed; otherwise a minimal KEY=VALUE parser is used.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
        return
    except Exception:
        pass
    # Fallback: look for .env next to the repo root and in the CWD.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [os.path.join(repo_root, ".env"), os.path.join(os.getcwd(), ".env")]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception:
            pass


@dataclass
class Config:
    backend_base_url: str = "http://localhost:8000"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "deepseek-chat"
    agent_mode: str = "hosp2mes"  # "hosp2mes" | "baseline"
    llm_provider: str = "mock"    # "mock" | "deepseek"
    policy: str = "deterministic"  # "deterministic" | "llm" | "llm-strict"
    publish_url: str = ""         # optional backend URL to stream traces to
    max_steps: int = 100
    frontend_url: str = "http://localhost:5173"   # Vue Mock MES base URL
    headless: bool = True                         # browser mode: headless Chromium
    artifacts_root: str = ""                      # evidence output root (artifacts/)

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv()
        # LLM credentials: prefer LLM_* (from .env), then fall back to the
        # OpenAI-style OPENAI_* variables (DeepSeek-compatible endpoints).
        return cls(
            backend_base_url=os.getenv("BACKEND_BASE_URL", "http://localhost:8000"),
            llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", ""),
            llm_model=os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "deepseek-chat"),
            agent_mode=os.getenv("AGENT_MODE", "hosp2mes"),
            llm_provider=os.getenv("AGENT_LLM_PROVIDER", "mock"),
            policy=os.getenv("AGENT_POLICY", "deterministic"),
            publish_url=os.getenv("AGENT_PUBLISH_URL", ""),
            max_steps=int(os.getenv("AGENT_MAX_STEPS", "100")),
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:5173"),
            headless=os.getenv("BROWSER_HEADLESS", "1") == "1",
            artifacts_root=os.getenv("AGENT_ARTIFACTS_ROOT", ""),
        )

    def use_real_llm(self) -> bool:
        return self.llm_provider == "deepseek" and bool(self.llm_api_key)

