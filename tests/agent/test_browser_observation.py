"""Unit tests for browser observation (dom_extractor + BrowserObservation)."""
from __future__ import annotations

import pytest

from hosp2mes.observation.browser_env import BrowserEnv

pytest.importorskip("playwright.sync_api")


_FORM_HTML = """
<html><body>
  <h1>物品主文件</h1>
  <form>
    <label for="code">物料编码</label>
    <input id="code" type="text" placeholder="请输入编码">
    <label>类型
      <input role="combobox" aria-label="类型">
    </label>
    <button aria-label="保存">保存</button>
    <button>取消</button>
  </form>
  <a href="/boms">BOM 管理</a>
</body></html>
"""


def test_browser_observation_extracts_semantic_elements(playwright_browser):
    env = BrowserEnv(base_url="http://localhost", _browser=playwright_browser)
    env.start()
    try:
        env._page.set_content(_FORM_HTML)
        obs = env.observe()

        assert obs.current_url.startswith("about:") or "localhost" in obs.current_url
        assert obs.title == ""
        assert "物品主文件" in obs.visible_text
        assert obs.timestamp

        names = [(e["role"], e["accessible_name"]) for e in obs.interactive_elements]
        # The text input is identified by its associated <label>.
        assert ("textbox", "物料编码") in names
        # The combobox carries an explicit aria-label.
        assert ("combobox", "类型") in names
        # Buttons are identified by their text / aria-label.
        assert ("button", "保存") in names
        assert ("button", "取消") in names
        # Links by their text.
        assert ("link", "BOM 管理") in names
    finally:
        env.close()


def test_browser_observation_screenshot_and_to_dict(playwright_browser):
    env = BrowserEnv(base_url="http://localhost", _browser=playwright_browser)
    env.start()
    try:
        env._page.set_content(_FORM_HTML)
        obs = env.observe()
        d = obs.to_dict()
        assert d["current_url"] == obs.current_url
        assert d["interactive_elements"] == obs.interactive_elements
        assert "screenshot_path" in d
        # screenshot_bytes is captured by observe()
        assert obs.screenshot_bytes is not None
    finally:
        env.close()


def test_browser_env_requires_start():
    env = BrowserEnv(base_url="http://localhost")
    with pytest.raises(RuntimeError):
        env.observe()
