"""Unit tests for the browser action executor (semantic locator resolution)."""
from __future__ import annotations

import pytest

from hosp2mes.executor.actions import Action
from hosp2mes.observation.browser_env import BrowserEnv

pytest.importorskip("playwright.sync_api")


_FORM_HTML = """
<html><body>
  <label for="code">物料编码</label>
  <input id="code" type="text">
  <button role="combobox" aria-label="类型">类型</button>
  <ul>
    <li role="option" aria-label="raw">raw</li>
    <li role="option" aria-label="solvent">solvent</li>
  </ul>
  <button id="submit">保存</button>
</body></html>
"""


def _env(playwright_browser):
    env = BrowserEnv(base_url="http://localhost", _browser=playwright_browser)
    env.start()
    env._page.set_content(_FORM_HTML)
    return env


def test_executor_type_by_label(playwright_browser):
    env = _env(playwright_browser)
    try:
        res = env.execute(Action("type", target="物料编码", value="MAT-1"))
        assert res.ok, res.detail
        assert env._page.locator("#code").input_value() == "MAT-1"
    finally:
        env.close()


def test_executor_click_button_by_name(playwright_browser):
    env = _env(playwright_browser)
    try:
        env._page.eval_on_selector(
            "#submit", "el => el.addEventListener('click', () => el.textContent = 'CLICKED')"
        )
        res = env.execute(Action("click", target="保存", params={"role": "button"}))
        assert res.ok, res.detail
        assert env._page.locator("#submit").inner_text() == "CLICKED"
    finally:
        env.close()


def test_executor_select_option(playwright_browser):
    env = _env(playwright_browser)
    try:
        res = env.execute(Action("select", target="类型", value="raw"))
        assert res.ok, res.detail
    finally:
        env.close()


def test_executor_extract(playwright_browser):
    env = _env(playwright_browser)
    try:
        res = env.execute(Action("extract"))
        assert res.ok
        assert "物料编码" in res.evidence["text"]
    finally:
        env.close()


def test_executor_missing_element_fails_cleanly(playwright_browser):
    env = _env(playwright_browser)
    try:
        res = env.execute(Action("click", target="不存在的按钮", params={"role": "button"}))
        assert not res.ok
        assert "no visible element" in res.detail
    finally:
        env.close()
