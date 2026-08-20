"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./mes_demo.db"

    # LLM (DeepSeek-compatible OpenAI-style chat completions)
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "deepseek-chat"

    # Agent behaviour
    agent_mode: str = "hosp2mes"  # "hosp2mes" | "baseline"
    agent_llm_provider: str = "mock"  # "mock" | "deepseek"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
