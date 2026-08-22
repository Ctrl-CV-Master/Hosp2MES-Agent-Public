"""Playwright-backed environment for real GUI execution.

``BrowserEnv`` is the *browser* realization of the environment seam. Unlike
``ApiEnv`` (which drives the Mock MES over its REST API), ``BrowserEnv`` opens
the Vue Mock MES in a real Chromium browser and performs business operations by
observing the page and acting on it through Playwright — clicking, typing,
selecting, waiting — exactly like a human operator.

Two hard rules are enforced by construction:

* **No REST for action decisions.** ``observe()`` reads only the rendered page.
  The MES REST API is never queried to decide the next action.
* **Independent verification only.** ``system_state()`` (used by the Evidence
  Verifier at the end of a run) reads the backend through a *separate,
  read-only* ``ApiEnv`` client. That client is never used to perform actions —
  it is the independent read-back that proves the GUI actually changed business
  state. Passing ``read_only=True`` makes it raise on any POST attempt.

The GUI action vocabulary is realized by :class:`~hosp2mes.executor.browser_executor.BrowserExecutor`.
"""
from __future__ import annotations

import os
import time
from typing import Any

from hosp2mes.observation.api_env import ActionResult, ApiEnv
from hosp2mes.observation.browser_observation import BrowserObservation
from hosp2mes.observation.dom_extractor import (
    extract_interactive_elements,
    extract_visible_text,
)

try:
    from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - playwright is an optional runtime dep
    _PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None  # type: ignore


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class BrowserEnv:
    """Real browser GUI environment backed by Playwright."""

    def __init__(
        self,
        base_url: str = "http://localhost:5173",
        backend_url: str | None = None,
        headless: bool = True,
        artifacts_dir: str | None = None,
        *,
        _pw: Any = None,
        _browser: Browser | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.backend_url = (backend_url or "http://localhost:8000").rstrip("/")
        self.headless = headless
        self.artifacts_dir = artifacts_dir
        self._pw = _pw
        self._injected_browser = _browser
        self._pw_ctx: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._started = False
        self._screenshot_seq = 0
        # Independent, read-only verification client (NEVER used for actions).
        self._verify_env = ApiEnv(base_url=self.backend_url, read_only=True)

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> "BrowserEnv":
        if self._started:
            return self
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "playwright is not installed. Run: pip install playwright "
                "&& playwright install chromium"
            )
        if self._injected_browser is not None:
            # Tests may inject a browser to share a single Chromium instance.
            self._browser = self._injected_browser
            self._pw_ctx = None
            self._context = self._browser.new_context()
        else:
            self._pw_ctx = self._pw or sync_playwright().start()
            self._browser = self._pw_ctx.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context()
        self._page = self._context.new_page()
        # Capture browser-side console / page errors so observation summaries
        # and failure messages always include the JS-side truth. The list is
        # capped to the last 200 entries to avoid unbounded growth.
        self.console_messages: list[str] = []

        def _on_console(msg) -> None:
            try:
                self.console_messages.append(f"[{msg.type}] {msg.text}")
            except Exception:
                return
            if len(self.console_messages) > 200:
                del self.console_messages[: len(self.console_messages) - 200]

        def _on_pageerror(exc) -> None:
            try:
                self.console_messages.append(f"[PAGEERROR] {exc}")
            except Exception:
                return

        self._page.on("console", _on_console)
        self._page.on("pageerror", _on_pageerror)
        self._started = True
        return self

    def reset(self) -> None:
        """Navigate back to the app root for a fresh run."""
        self._require_page()
        self._page.goto(self.base_url + "/", wait_until="domcontentloaded")

    def close(self) -> None:
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        if self._injected_browser is None and self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw_ctx is not None:
            try:
                self._pw_ctx.stop()
            except Exception:
                pass
        self._started = False
        self._page = None
        self._context = None
        self._browser = None

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserEnv not started; call start() first")
        return self._page

    # ---- observation -----------------------------------------------------
    def observe(self) -> BrowserObservation:
        page = self._require_page()
        elements = extract_interactive_elements(page)
        screenshot_path, screenshot_bytes = self._capture("observe")
        return BrowserObservation(
            current_url=page.url,
            title=page.title(),
            visible_text=extract_visible_text(page),
            interactive_elements=elements,
            accessibility=elements,
            screenshot_path=screenshot_path,
            screenshot_bytes=screenshot_bytes,
            timestamp=_now(),
        )

    def get_current_url(self) -> str:
        return self._require_page().url

    # ---- screenshots -----------------------------------------------------
    def screenshot(self, name: str | None = None) -> tuple[str | None, bytes | None]:
        return self._capture(name or "screenshot")

    def _capture(self, label: str) -> tuple[str | None, bytes | None]:
        page = self._require_page()
        try:
            png = page.screenshot(type="png")
        except Exception:
            return None, None
        self._screenshot_seq += 1
        path: str | None = None
        if self.artifacts_dir:
            os.makedirs(self.artifacts_dir, exist_ok=True)
            safe = label.replace("/", "_").replace("\\", "_").replace(" ", "_")
            path = os.path.join(
                self.artifacts_dir, f"{self._screenshot_seq:03d}-{safe}.png"
            )
            try:
                with open(path, "wb") as f:
                    f.write(png)
            except Exception:
                path = None
        return path, png

    # ---- actions ---------------------------------------------------------
    def execute(self, action) -> ActionResult:
        """Execute a structured GUI action through Playwright.

        ``action`` is an :class:`~hosp2mes.executor.actions.Action`. The actual
        locator resolution lives in the BrowserExecutor so the agent never
        touches raw Playwright selectors.
        """
        from hosp2mes.executor.browser_executor import BrowserExecutor

        return BrowserExecutor().execute(action, self)

    # ---- independent verification (read-only, final state only) ----------
    def system_state(self, product: str | None = None,
                     material_code: str | None = None) -> dict:
        """Independent business-state read-back via a read-only REST client.

        This is the ONLY place the backend is contacted in browser mode, and it
        is used exclusively for the final evidence-gated verification. It can
        never perform a business operation.
        """
        return self._verify_env.system_state(product=product, material_code=material_code)

    def get_material(self, code: str) -> dict | None:
        return self._verify_env.get_material(code)

    def get_bom(self, bom_code: str) -> dict | None:
        return self._verify_env.get_bom(bom_code)

    def get_order(self, order_code: str) -> dict | None:
        return self._verify_env.get_order(order_code)
