"""Browser action executor: structured GUI actions -> Playwright operations.

This is the *only* place in browser mode that touches Playwright locators. The
business agent emits abstract :class:`~hosp2mes.executor.actions.Action` objects
(``click`` / ``type`` / ``select`` / ``wait`` / ...) and this executor resolves
them to real DOM elements **by semantics** — role + accessible name, label text,
placeholder text — never by hand-written XPath/CSS, never by fixed coordinates
or ``nth`` indices.

Resolution order for a target name is deliberately lenient and human-like:

  1. exact accessible-name match via ``get_by_role``
  2. substring accessible-name match
  3. ``get_by_label`` (label association / Element-Plus form item label)
  4. ``get_by_placeholder``

A target may also be a *scoped* dict, which the executor resolves against the
*fresh* current DOM every time::

    Action("click", target={
        "within": {"role": "row", "text": "过滤"},
        "role": "button", "name": "完成",
    })

The executor first locates the semantic container (the row whose accessible
text contains "过滤"), then searches *inside* that container for the button
named "完成". Because every action re-resolves from the live page, stale
ElementHandles across Vue re-renders are never reused.

``wait`` supports state-based synchronization instead of fixed sleeps::

    Action("wait", params={"for": "disabled", "role": "button", "name": "完成称量"})

Conditions: ``visible`` / ``hidden`` / ``detached`` / ``enabled`` / ``disabled`` /
``text_contains`` / ``text_not_contains``.
"""
from __future__ import annotations

import re
import time
from typing import Any

from playwright.sync_api import Locator, Page

from hosp2mes.executor.actions import Action
from hosp2mes.observation.api_env import ActionResult


class _LocatorMiss(Exception):
    def __init__(self, role: str, name: str):
        super().__init__(f"no visible element found for role={role!r} name={name!r}")
        self.role = role
        self.name = name


class _ConditionTimeout(Exception):
    pass


class BrowserExecutor:
    """Translate an abstract GUI Action into a Playwright interaction."""

    def execute(self, action: Action, env) -> ActionResult:
        page: Page = env._require_page()
        verb = (action.verb or "").strip().lower()
        target = action.target
        value = action.value
        params = action.params or {}

        handler = getattr(self, f"_do_{verb}", None)
        if handler is None:
            return ActionResult(ok=False, action=action.summary(),
                                detail=f"unknown browser verb: {verb}")
        try:
            detail, evidence = handler(page, action, target, value, params)
            return ActionResult(ok=True, action=action.summary(),
                                detail=detail, evidence=evidence)
        except _LocatorMiss as exc:
            return ActionResult(ok=False, action=action.summary(),
                                detail=str(exc), evidence={})
        except Exception as exc:  # noqa: BLE001 - surface any DOM failure honestly
            return ActionResult(ok=False, action=action.summary(),
                                detail=f"{type(exc).__name__}: {exc}", evidence={})

    # ---- target parsing --------------------------------------------------
    @staticmethod
    def _target_parts(target: Any, params: dict) -> tuple[str, str | None, dict | None]:
        """Split a target (str or scoped dict) into (name, role, within)."""
        if isinstance(target, dict):
            name = target.get("name") or target.get("text") or ""
            role = target.get("role")
            within = target.get("within")
        else:
            name = (target or "").strip()
            role = None
            within = None
        role = role or params.get("role")
        within = within or params.get("within")
        return name, role, within

    # ---- action handlers -------------------------------------------------
    def _do_navigate(self, page, action, target, value, params):
        url = target
        if url and not url.startswith("http"):
            base = params.get("base_url") or _base_url_from_page(page)
            url = base.rstrip("/") + "/" + url.lstrip("/")
        page.goto(url or (params.get("base_url") or page.url),
                  wait_until=params.get("wait_until", "domcontentloaded"))
        return f"navigated to {url}", {"url": page.url}

    def _do_back(self, page, action, target, value, params):
        page.go_back(wait_until="domcontentloaded")
        return "went back", {"url": page.url}

    def _do_click(self, page, action, target, value, params):
        name, role, within = self._target_parts(target, params)
        role = role or "button"
        loc = self._resolve(page, role, name, params, within)
        if params.get("first_enabled"):
            loc = _first_enabled(loc)
        loc.click(timeout=params.get("timeout", 5000))
        return f"clicked {role} '{name}'", {"role": role, "target": _plain(target)}

    def _do_type(self, page, action, target, value, params):
        name, _role, within = self._target_parts(target, params)
        loc = self._resolve_field(page, name, params, within)
        loc.click(timeout=params.get("timeout", 5000))
        loc.fill("" if params.get("clear") else str(value or ""))
        if params.get("press_enter"):
            loc.press("Enter")
        return f"typed '{value}' into '{name}'", {"target": _plain(target)}

    def _do_input(self, page, action, target, value, params):
        # Alias of ``type`` (the spec lists both ``input`` and ``type``).
        return self._do_type(page, action, target, value, params)

    def _do_press(self, page, action, target, value, params):
        key = value or (target if isinstance(target, str) else "") or "Enter"
        loc = None
        if isinstance(target, str) and target:
            loc = self._resolve_field(page, target, params)
        if loc is not None:
            loc.press(key)
        else:
            page.keyboard.press(key)
        return f"pressed {key}", {"key": key}

    def _do_select(self, page, action, target, value, params):
        # Element-Plus <el-select> renders a combobox; choose the option text.
        name, _role, within = self._target_parts(target, params)
        combobox = self._resolve(page, "combobox", name, params, within)
        # Element Plus decorates the combobox input with a placeholder /
        # selected-item overlay that intercepts pointer events. The semantic
        # click target is the visible control — the wrapper or the overlay —
        # not the hidden input itself, so use force=True on the first click.
        combobox.click(force=True, timeout=params.get("timeout", 5000))
        page.wait_for_timeout(params.get("dropdown_wait", 400))
        option = self._resolve_option(page, str(value))
        option.click(timeout=params.get("timeout", 5000))
        return f"selected '{value}' in '{name}'", {"target": _plain(target), "value": value}

    def _do_wait(self, page, action, target, value, params):
        condition = params.get("for") or params.get("condition")
        if condition:
            return self._wait_condition(page, target, value, params)
        ms = value if isinstance(value, int) else int(params.get("ms", value or 1000))
        page.wait_for_timeout(ms)
        return f"waited {ms}ms", {"ms": ms}

    def _do_scroll(self, page, action, target, value, params):
        name, role, within = self._target_parts(target, params)
        if name:
            loc = self._resolve(page, role or "generic", name, params, within)
            loc.scroll_into_view_if_needed(timeout=params.get("timeout", 5000))
        else:
            dy = value if isinstance(value, int) else int(params.get("dy", 0))
            page.mouse.wheel(0, dy)
        return "scrolled", {"target": _plain(target)}

    def _do_extract(self, page, action, target, value, params):
        name, role, within = self._target_parts(target, params)
        if name:
            loc = self._resolve(page, role or "generic", name, params, within)
            text = loc.inner_text(timeout=params.get("timeout", 5000))
        else:
            text = page.locator("body").inner_text(timeout=params.get("timeout", 5000))
        return "extracted text", {"text": text}

    # ---- state-based wait ------------------------------------------------
    def _wait_condition(self, page, target, value, params):
        condition = params.get("for") or params.get("condition")
        name, role, within = self._target_parts(target, params)
        role = role or params.get("role") or "button"
        timeout_ms = params.get("timeout", 8000)
        poll_ms = params.get("poll", 100)

        deadline = time.time() + timeout_ms / 1000.0
        last_state: dict | None = None
        while time.time() < deadline:
            state = self._condition_state(page, role, name, within, params)
            last_state = state
            if _condition_met(condition, state, value):
                return (
                    f"condition '{condition}' met for {role} '{name}'",
                    {"condition": condition, "state": state},
                )
            page.wait_for_timeout(poll_ms)
        raise _ConditionTimeout(
            f"condition '{condition}' not met for role={role!r} name={name!r} "
            f"within {timeout_ms}ms; last state={last_state}"
        )

    def _condition_state(self, page, role, name, within, params) -> dict:
        try:
            if name:
                loc = self._resolve(page, role, name, params, within)
            elif within is not None:
                loc = self._resolve_container(page, within, params).get_by_role(role)
            else:
                loc = page.get_by_role(role)
        except _LocatorMiss:
            loc = None
        if loc is None:
            return {"count": 0, "visible": False, "disabled": None, "text": ""}
        el = _first_visible(loc)
        if el is None:
            return {"count": loc.count(), "visible": False, "disabled": None, "text": ""}
        try:
            text = el.inner_text()
        except Exception:
            text = ""
        try:
            disabled = el.is_disabled()
        except Exception:
            disabled = None
        return {"count": loc.count(), "visible": True, "disabled": disabled, "text": text}

    # ---- locator resolution ---------------------------------------------
    def _resolve(self, page: Page, role: str, name: str, params: dict,
                 within: dict | None = None) -> Locator:
        """Find a *visible* element by role + accessible name (with fallbacks).

        Scoping order:

        1. ``within`` container (explicit semantic scope from the action);
        2. the topmost open modal dialog (role=dialog) — so duplicate-labelled
           controls in the page underneath are never targeted;
        3. page-wide.
        """
        name = (name or "").strip()
        if not name:
            raise _LocatorMiss(role, name)

        if within is not None:
            container = self._resolve_container(page, within, params)
            return self._resolve_in_scope(container, role, name, params,
                                          scope_hint=f"{within.get('role', 'row')} '{within.get('text') or within.get('name') or ''}'")

        dialog = _topmost_dialog(page)
        exact = bool(params.get("exact", False))

        if dialog is not None:
            # If a dialog is open, resolve strictly inside it — don't fall
            # through to duplicate-labelled controls in the page underneath.
            return self._resolve_in_scope(dialog, role, name, params,
                                          scope_hint="dialog", exact=exact)

        # Page-wide resolution.
        candidate = page.get_by_role(role, name=name, exact=exact)
        found = _first_visible(candidate)
        if found is not None:
            return found

        try:
            fuzzy = page.get_by_role(role, name=re.compile(re.escape(name), re.IGNORECASE))
            found = _first_visible(fuzzy)
            if found is not None:
                return found
        except Exception:
            pass

        if role in ("textbox", "combobox", "spinbutton", "generic"):
            for getter in (
                lambda: page.get_by_label(name, exact=exact),
                lambda: page.get_by_placeholder(name),
            ):
                try:
                    found = _first_visible(getter())
                    if found is not None:
                        return found
                except Exception:
                    continue

        raise _LocatorMiss(role, name)

    def _resolve_field(self, page: Page, name: str, params: dict,
                       within: dict | None = None) -> Locator:
        """Resolve an input/select field by its label/placeholder/name."""
        name = (name or "").strip()
        if not name:
            raise _LocatorMiss("field", name)

        if within is not None:
            container = self._resolve_container(page, within, params)
            return self._resolve_field_in_scope(container, name, params,
                                                scope_hint=f"{within.get('role', 'row')} '{within.get('text') or ''}'")

        dialog = _topmost_dialog(page)
        if dialog is not None:
            return self._resolve_field_in_scope(dialog, name, params, scope_hint="dialog")

        return self._resolve_field_in_scope(page, name, params)

    def _resolve_container(self, page: Page, spec: dict, params: dict) -> Locator:
        """Resolve a semantic container (e.g. a table row) by role + text."""
        role = spec.get("role", "row")
        text = (spec.get("text") or spec.get("name") or "").strip()
        if not text:
            raise _LocatorMiss(role, "(no container text)")

        # Accessible-name substring match (rows expose their cell text).
        try:
            c = page.get_by_role(role, name=re.compile(re.escape(text), re.IGNORECASE))
            found = _first_visible(c)
            if found is not None:
                return found
        except Exception:
            pass
        # Fallback: filter by contained text.
        try:
            c = page.get_by_role(role).filter(has_text=re.compile(re.escape(text), re.IGNORECASE))
            found = _first_visible(c)
            if found is not None:
                return found
        except Exception:
            pass
        raise _LocatorMiss(role, text)

    def _resolve_in_scope(self, scope: Locator, role: str, name: str,
                          params: dict, scope_hint: str = "", exact: bool = False) -> Locator:
        for getter in (
            lambda: scope.get_by_role(role, name=name, exact=exact),
            lambda: scope.get_by_role(role, name=re.compile(re.escape(name), re.IGNORECASE)),
            lambda: scope.get_by_label(name, exact=exact),
        ):
            try:
                found = _first_visible(getter())
                if found is not None:
                    return found
            except Exception:
                continue
        raise _LocatorMiss(role, f"{name} (within {scope_hint})")

    def _resolve_field_in_scope(self, scope: Locator, name: str, params: dict,
                                scope_hint: str = "") -> Locator:
        for getter in (
            lambda: scope.get_by_label(name),
            lambda: scope.get_by_role("textbox", name=name),
            lambda: scope.get_by_role("combobox", name=name),
            lambda: scope.get_by_role("spinbutton", name=name),
            lambda: scope.get_by_placeholder(name),
        ):
            try:
                found = _first_visible(getter())
                if found is not None:
                    return found
            except Exception:
                continue
        raise _LocatorMiss("field", f"{name} (within {scope_hint})")

    def _resolve_option(self, page: Page, text: str) -> Locator:
        option = page.get_by_role("option", name=text)
        found = _first_visible(option)
        if found is not None:
            return found
        try:
            fuzzy = page.get_by_role(
                "option", name=re.compile(re.escape(text), re.IGNORECASE)
            )
            found = _first_visible(fuzzy)
            if found is not None:
                return found
        except Exception:
            pass
        found = _first_visible(page.get_by_text(text, exact=True))
        if found is not None:
            return found
        raise _LocatorMiss("option", text)


def _plain(target: Any) -> str:
    if isinstance(target, dict):
        return target.get("name") or target.get("text") or ""
    return str(target)


def _condition_met(condition: str, state: dict, value: Any) -> bool:
    if condition == "visible":
        return state.get("visible") is True
    if condition == "hidden":
        return state.get("visible") is not True
    if condition == "detached":
        return state.get("count", 0) == 0
    if condition == "enabled":
        return state.get("visible") is True and state.get("disabled") is False
    if condition == "disabled":
        return state.get("visible") is True and state.get("disabled") is True
    if condition == "text_contains":
        return (str(value or "")) in (state.get("text") or "")
    if condition == "text_not_contains":
        return (str(value or "")) not in (state.get("text") or "")
    raise ValueError(f"unknown wait condition: {condition}")


def _first_visible(loc: Locator) -> Locator | None:
    """Return the first visible element of a locator set, or None."""
    try:
        n = loc.count()
    except Exception:
        return None
    for i in range(n):
        el = loc.nth(i)
        try:
            if el.is_visible():
                return el
        except Exception:
            continue
    return None


def _topmost_dialog(page: Page) -> Locator | None:
    """Return the topmost visible modal dialog element, or None.

    "Topmost" is approximated as the last visible dialog in DOM order, which
    matches Element-Plus' stacking for sequentially opened dialogs.
    """
    try:
        dialogs = page.get_by_role("dialog")
        n = dialogs.count()
    except Exception:
        return None
    last: Locator | None = None
    for i in range(n):
        d = dialogs.nth(i)
        try:
            if d.is_visible():
                last = d
        except Exception:
            continue
    return last


def _first_enabled(loc: Locator) -> Locator:
    """Return the first *enabled* (non-disabled) element of a locator set."""
    n = loc.count()
    for i in range(n):
        el = loc.nth(i)
        try:
            if not el.is_disabled() and el.is_visible():
                return el
        except Exception:
            continue
    return loc.first


def _base_url_from_page(page: Page) -> str:
    url = page.url
    import urllib.parse

    parts = urllib.parse.urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"
