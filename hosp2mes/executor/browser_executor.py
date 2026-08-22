"""Browser action executor: structured GUI actions -> Playwright operations.

This is the *only* place in browser mode that touches Playwright locators. The
business agent emits abstract :class:`~hosp2mes.executor.actions.Action` objects
(``click`` / ``type`` / ``select`` / ...) and this executor resolves them to
real DOM elements **by semantics** — role + accessible name, label text,
placeholder text — never by hand-written XPath/CSS.

Resolution order for a target name is deliberately lenient and human-like:

  1. exact accessible-name match via ``get_by_role``
  2. substring accessible-name match
  3. ``get_by_label`` (label association / Element-Plus form item label)
  4. ``get_by_placeholder``

This keeps the executor generic: it works on any Element-Plus form with proper
labels, and is not hardcoded to a specific task id or click sequence.
"""
from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Locator, Page

from hosp2mes.executor.actions import Action
from hosp2mes.observation.api_env import ActionResult


class _LocatorMiss(Exception):
    def __init__(self, role: str, name: str):
        super().__init__(f"no visible element found for role={role!r} name={name!r}")
        self.role = role
        self.name = name


class BrowserExecutor:
    """Translate an abstract GUI Action into a Playwright interaction."""

    def execute(self, action: Action, env) -> ActionResult:
        page: Page = env._require_page()
        verb = (action.verb or "").strip().lower()
        target = (action.target or "").strip()
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
        role = params.get("role") or "button"
        loc = self._resolve(page, role, target, params)
        if params.get("first_enabled"):
            loc = _first_enabled(loc)
        loc.click(timeout=params.get("timeout", 5000))
        return f"clicked {role} '{target}'", {"role": role, "target": target}

    def _do_type(self, page, action, target, value, params):
        loc = self._resolve_field(page, target, params)
        loc.click(timeout=params.get("timeout", 5000))
        loc.fill("" if params.get("clear") else str(value or ""))
        if params.get("press_enter"):
            loc.press("Enter")
        return f"typed '{value}' into '{target}'", {"target": target}

    def _do_input(self, page, action, target, value, params):
        # Alias of ``type`` (the spec lists both ``input`` and ``type``).
        return self._do_type(page, action, target, value, params)

    def _do_press(self, page, action, target, value, params):
        key = value or target or "Enter"
        loc = None
        if target:
            loc = self._resolve_field(page, target, params)
        if loc is not None:
            loc.press(key)
        else:
            page.keyboard.press(key)
        return f"pressed {key}", {"key": key}

    def _do_select(self, page, action, target, value, params):
        # Element-Plus <el-select> renders a combobox; choose the option text.
        combobox = self._resolve(page, "combobox", target, params)
        # Element Plus decorates the combobox input with a placeholder /
        # selected-item overlay that intercepts pointer events. The semantic
        # click target is the visible control — the wrapper or the overlay —
        # not the hidden input itself, so use force=True on the first click.
        combobox.click(force=True, timeout=params.get("timeout", 5000))
        page.wait_for_timeout(params.get("dropdown_wait", 400))
        option = self._resolve_option(page, str(value))
        option.click(timeout=params.get("timeout", 5000))
        return f"selected '{value}' in '{target}'", {"target": target, "value": value}

    def _do_wait(self, page, action, target, value, params):
        ms = value if isinstance(value, int) else int(params.get("ms", value or 1000))
        page.wait_for_timeout(ms)
        return f"waited {ms}ms", {"ms": ms}

    def _do_scroll(self, page, action, target, value, params):
        if target:
            loc = self._resolve(page, params.get("role", "generic"), target, params)
            loc.scroll_into_view_if_needed(timeout=params.get("timeout", 5000))
        else:
            dy = value if isinstance(value, int) else int(params.get("dy", 0))
            page.mouse.wheel(0, dy)
        return "scrolled", {"target": target}

    def _do_extract(self, page, action, target, value, params):
        if target:
            loc = self._resolve(page, params.get("role", "generic"), target, params)
            text = loc.inner_text(timeout=params.get("timeout", 5000))
        else:
            text = page.locator("body").inner_text(timeout=params.get("timeout", 5000))
        return "extracted text", {"text": text}

    # ---- locator resolution ---------------------------------------------
    def _resolve(self, page: Page, role: str, name: str, params: dict) -> Locator:
        """Find a *visible* element by role + accessible name (with fallbacks).

        When a modal dialog (role=dialog) is currently open, lookups are
        scoped to the topmost dialog so we don't accidentally interact with
        duplicate-labelled controls in the page underneath (e.g. the BOM
        page's "产品" filter vs. the BOM dialog's "产品" input).
        """
        name = (name or "").strip()
        if not name:
            raise _LocatorMiss(role, name)

        dialog = _topmost_dialog(page)
        exact = bool(params.get("exact", False))

        # First, try within the dialog (if any) using the role+name match.
        if dialog is not None:
            scoped = dialog.get_by_role(role, name=name, exact=exact)
            found = _first_visible(scoped)
            if found is not None:
                return found
            # Fallback scoped to label / placeholder.
            if role in ("textbox", "combobox", "spinbutton", "generic"):
                for getter in (
                    lambda: dialog.get_by_label(name, exact=exact),
                    lambda: dialog.get_by_placeholder(name),
                ):
                    try:
                        found = _first_visible(getter())
                        if found is not None:
                            return found
                    except Exception:
                        continue
            # If the target is unique to the dialog and not found, surface a
            # clear error (don't fall through to the page underneath).
            raise _LocatorMiss(role, name + " (in open dialog)")

        # No dialog open -> page-wide resolution (original behaviour).
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

    def _resolve_field(self, page: Page, name: str, params: dict) -> Locator:
        """Resolve an input/select field by its label/placeholder/name.

        When a modal dialog is open, the lookup is scoped to the dialog so we
        never target the page underneath (which often carries duplicate
        labels).
        """
        name = (name or "").strip()
        if not name:
            raise _LocatorMiss("field", name)

        dialog = _topmost_dialog(page)
        if dialog is not None:
            for getter in (
                lambda: dialog.get_by_label(name),
                lambda: dialog.get_by_role("textbox", name=name),
                lambda: dialog.get_by_role("combobox", name=name),
                lambda: dialog.get_by_role("spinbutton", name=name),
                lambda: dialog.get_by_placeholder(name),
            ):
                try:
                    found = _first_visible(getter())
                    if found is not None:
                        return found
                except Exception:
                    continue
            raise _LocatorMiss("field", name + " (in open dialog)")

        for getter in (
            lambda: page.get_by_label(name),
            lambda: page.get_by_role("textbox", name=name),
            lambda: page.get_by_role("combobox", name=name),
            lambda: page.get_by_role("spinbutton", name=name),
            lambda: page.get_by_placeholder(name),
        ):
            try:
                found = _first_visible(getter())
                if found is not None:
                    return found
            except Exception:
                continue

        raise _LocatorMiss("field", name)

    def _resolve_option(self, page: Page, text: str) -> Locator:
        option = page.get_by_role("option", name=text)
        found = _first_visible(option)
        if found is not None:
            return found
        # Substring match on the option's accessible name (e.g. an order code
        # embedded in an option label "ORD-123 · PRODUCT").
        try:
            fuzzy = page.get_by_role(
                "option", name=re.compile(re.escape(text), re.IGNORECASE)
            )
            found = _first_visible(fuzzy)
            if found is not None:
                return found
        except Exception:
            pass
        # Element-Plus option fallback: exact text node inside the dropdown.
        found = _first_visible(page.get_by_text(text, exact=True))
        if found is not None:
            return found
        raise _LocatorMiss("option", text)


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


def _has_visible(loc: Locator) -> bool:
    return _first_visible(loc) is not None


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
