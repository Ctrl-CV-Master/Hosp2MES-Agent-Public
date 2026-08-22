"""Agent S3 adapter — wires the *official* Agent S3 to the Hosp2MES browser env.

Agent S3 is Simular AI's open-source computer-use GUI agent
(https://github.com/simular-ai/Agent-S, Apache-2.0, PyPI package ``gui-agents``).
This adapter is a thin, honest bridge between that framework and our
Playwright-backed ``BrowserEnv``:

    BrowserObservation (screenshot + accessibility text)
        -> AgentS3.predict(instruction, obs)
        -> (info, actions)
        -> best-effort mapping to a BrowserExecutor Action

It imports the **real** ``gui_agents.s3.agents.agent_s.AgentS3`` and
``gui_agents.s3.agents.grounding.OSWorldACI`` classes — it is NOT a mock.

Hard requirements for a *real* prediction (documented honestly):

1. ``gui-agents`` installed (it pulls ``paddlepaddle``/``paddleocr``/``pyautogui``/
   ``pytesseract``/``pywinauto``; Python <=3.12; tesseract binary).
2. A worker LLM provider + API key (OpenAI/Anthropic/Gemini/...).
3. A visual-grounding model endpoint (UI-TARS-1.5-7B) served via HF/vLLM/TGI.

Without these, constructing the agent raises a clear error — it never fakes a
successful prediction.
"""
from __future__ import annotations

import base64
from typing import Any

from hosp2mes.config import Config
from hosp2mes.observation.browser_observation import BrowserObservation

# Canonical facts verified from the official repo (do not edit casually).
AGENT_S3_REPO = "https://github.com/simular-ai/Agent-S"
AGENT_S3_PYPI = "gui-agents"
AGENT_S3_LICENSE = "Apache-2.0"
AGENT_S3_IMPORT = "gui_agents.s3.agents.agent_s"


class AgentS3Unavailable(RuntimeError):
    """Raised when Agent S3 cannot be constructed (missing deps / credentials)."""


class AgentS3Adapter:
    """Bridge BrowserEnv -> official Agent S3 -> BrowserExecutor action."""

    def __init__(
        self,
        config: Config,
        *,
        worker_engine_params: dict | None = None,
        grounding_engine_params: dict | None = None,
        platform: str = "windows",
        width: int = 1920,
        height: int = 1080,
        max_trajectory_length: int = 8,
        enable_reflection: bool = True,
        env: Any = None,
    ):
        self.config = config
        self.platform = platform.lower()
        self.width = width
        self.height = height
        self._worker_engine_params = worker_engine_params or _default_worker_params(config)
        self._grounding_engine_params = grounding_engine_params or {}
        self._env = env
        self._max_trajectory_length = max_trajectory_length
        self._enable_reflection = enable_reflection
        self._agent = None

    # ---- availability ----------------------------------------------------
    @staticmethod
    def is_installed() -> bool:
        try:
            import gui_agents  # noqa: F401

            return True
        except Exception:
            return False

    # ---- construction ----------------------------------------------------
    def _ensure_agent(self):
        if self._agent is not None:
            return self._agent

        if not self.is_installed():
            raise AgentS3Unavailable(
                f"gui-agents is not installed. Run: pip install {AGENT_S3_PYPI}. "
                f"(repo {AGENT_S3_REPO}, license {AGENT_S3_LICENSE})"
            )
        if not self._grounding_engine_params:
            raise AgentS3Unavailable(
                "Agent S3 requires a visual-grounding model endpoint "
                "(grounding_engine_params / UI-TARS). Provide it to construct the agent."
            )

        from gui_agents.s3.agents.agent_s import AgentS3
        from gui_agents.s3.agents.grounding import OSWorldACI

        grounding_agent = OSWorldACI(
            env=self._env,
            platform=self.platform,
            engine_params_for_generation=self._worker_engine_params,
            engine_params_for_grounding=self._grounding_engine_params,
            width=self.width,
            height=self.height,
        )
        self._agent = AgentS3(
            worker_engine_params=self._worker_engine_params,
            grounding_agent=grounding_agent,
            platform=self.platform,
            max_trajectory_length=self._max_trajectory_length,
            enable_reflection=self._enable_reflection,
        )
        return self._agent

    # ---- prediction ------------------------------------------------------
    def predict(self, instruction: str, observation: BrowserObservation):
        """Return ``(info, actions)`` from the *real* AgentS3.predict()."""
        agent = self._ensure_agent()
        obs = self.to_s3_observation(observation)
        return agent.predict(instruction=instruction, obs=obs)

    @staticmethod
    def to_s3_observation(observation: BrowserObservation) -> dict:
        """Convert a BrowserObservation into Agent S3's observation dict.

        Agent S3 is vision-based: the only field it truly consumes is
        ``screenshot`` (base64 PNG). We additionally attach the accessibility /
        semantic text we already extract from the DOM (harmless, and useful for
        the grounding model's OCR path).
        """
        if observation.screenshot_bytes:
            b64 = base64.b64encode(observation.screenshot_bytes).decode("ascii")
        elif observation.screenshot_path:
            with open(observation.screenshot_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
        else:
            b64 = ""

        a11y = "\n".join(
            f"{e.get('role', '?')}\t{e.get('accessible_name') or e.get('text')}"
            for e in observation.interactive_elements
        )
        return {
            "screenshot": b64,
            "accessibility_tree": a11y,
            "ocr_text": observation.visible_text,
        }

    # ---- action mapping (best effort) -----------------------------------
    @staticmethod
    def map_action_to_browser(action: Any):
        """Best-effort map an Agent S3 action to a BrowserExecutor Action.

        Agent S3 emits coordinate / pyautogui-style actions, which are
        fundamentally different from our semantic DOM actions. This mapping only
        translates the verbs it can express semantically; everything else is
        returned as-is for the caller to handle. It never fabricates a
        successful translation.
        """
        if isinstance(action, dict):
            verb = action.get("action") or action.get("type")
            return _S3_VERB_MAP.get(str(verb).lower(), action)
        if isinstance(action, str):
            for key, verb in (("click", "click"), ("type", "type"), ("press", "press"),
                              ("scroll", "scroll"), ("wait", "wait"), ("done", "done")):
                if action.lower().startswith(key):
                    return {"action": verb, "raw": action}
        return {"raw": action}


_S3_VERB_MAP = {
    "click": "click",
    "type": "type",
    "press": "press",
    "hotkey": "press",
    "scroll": "scroll",
    "wait": "wait",
    "done": "done",
}


def _default_worker_params(config: Config) -> dict:
    return {
        "engine_type": config.llm_provider or "openai",
        "model": config.llm_model or "gpt-5-2025-08-07",
        "api_key": config.llm_api_key or None,
        "base_url": config.llm_base_url or None,
    }
