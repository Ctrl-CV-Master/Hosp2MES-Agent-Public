"""DOM / accessibility extraction for browser observations.

We deliberately do **not** rely on Playwright's now-removed ``page.accessibility``
API (which no longer ships in current Playwright versions). Instead we run a
small, self-contained JavaScript probe in the page that walks the interactive
controls and computes a reasonable *accessible name* for each one using the same
heuristics a screen reader uses:

  1. ``aria-label`` / ``aria-labelledby``
  2. an associated ``<label for=id>``
  3. a wrapping ``<label>``
  4. the Element-Plus ``.el-form-item__label`` text (common in this Mock MES UI)
  5. ``placeholder`` / ``title`` / visible text

This gives the agent the semantic information ("a button named 新建物料", "a
textbox labelled 物料编码") it needs to decide actions without hardcoded
XPath/CSS selectors.
"""
from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

# Roles we treat as interactive, with a fallback role per tag name.
_TAG_ROLE = {
    "BUTTON": "button",
    "A": "link",
    "INPUT": "textbox",
    "TEXTAREA": "textbox",
    "SELECT": "combobox",
    "OPTION": "option",
}

# Input types that are not plain text boxes.
_INPUT_TYPE_ROLE = {
    "checkbox": "checkbox",
    "radio": "radio",
    "submit": "button",
    "reset": "button",
    "button": "button",
    "number": "spinbutton",
    "range": "slider",
}


_EXTRACTOR_JS = r"""
() => {
  const tagRole = (el) => {
    const t = el.tagName.toUpperCase();
    if (t === "INPUT") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      return {
        "checkbox": "checkbox", "radio": "radio", "submit": "button",
        "reset": "button", "button": "button", "number": "spinbutton",
        "range": "slider",
      }[type] || "textbox";
    }
    if (t === "TEXTAREA") return "textbox";
    if (t === "SELECT") return "combobox";
    if (t === "OPTION") return "option";
    if (t === "BUTTON") return "button";
    if (t === "A" && el.getAttribute("href")) return "link";
    if (t === "IMG") return "img";
    return "generic";
  };

  const visible = (el) => {
    const style = window.getComputedStyle(el);
    if (!el.getClientRects().length) return false;
    if (style.visibility === "hidden" || style.display === "none") return false;
    if (parseFloat(style.opacity || "1") === 0) return false;
    return true;
  };

  const textOf = (el) => (el.textContent || "").replace(/\s+/g, " ").trim();

  const elFormItemLabel = (el) => {
    let node = el;
    for (let i = 0; i < 6 && node; i++) {
      const item = node.closest && node.closest(".el-form-item");
      if (item) {
        const lbl = item.querySelector(".el-form-item__label");
        if (lbl && textOf(lbl)) return textOf(lbl);
      }
      node = node.parentElement;
    }
    return "";
  };

  const accessibleName = (el) => {
    const ariaLabel = (el.getAttribute("aria-label") || "").trim();
    if (ariaLabel) return ariaLabel;
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const names = labelledBy.split(/\s+/).map(id => {
        const ref = document.getElementById(id);
        return ref ? textOf(ref) : "";
      }).filter(Boolean);
      if (names.length) return names.join(" ");
    }
    const id = el.getAttribute("id");
    if (id) {
      const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (label) {
        const t = textOf(label);
        if (t) return t;
      }
    }
    if (el.closest && el.closest("label")) {
      const t = textOf(el.closest("label"));
      if (t) return t;
    }
    const formLabel = elFormItemLabel(el);
    if (formLabel) return formLabel;
    const placeholder = (el.getAttribute("placeholder") || "").trim();
    if (placeholder) return placeholder;
    const title = (el.getAttribute("title") || "").trim();
    if (title) return title;
    // Fall back to the element's own text content (the accessible name of a
    // <button>/<a>/<option> is its content; inputs are void so this is "").
    return textOf(el);
  };

  const selectors = [
    "button", "a[href]", "input", "select", "textarea",
    "[role]", "[tabindex]", "[contenteditable='true']",
  ];

  const seen = new Set();
  const out = [];
  for (const sel of selectors) {
    document.querySelectorAll(sel).forEach((el) => {
      if (seen.has(el)) return;
      seen.add(el);
      const role = el.getAttribute("role") || tagRole(el);
      const name = accessibleName(el);
      const text = textOf(el);
      // Only report controls that carry a usable identity (name or text).
      const identity = name || text;
      out.push({
        tag: el.tagName.toLowerCase(),
        role: role,
        accessible_name: name,
        text: text.slice(0, 120),
        placeholder: (el.getAttribute("placeholder") || "").trim(),
        aria_label: (el.getAttribute("aria-label") || "").trim(),
        input_type: el.getAttribute("type") || "",
        id: el.getAttribute("id") || "",
        disabled: !!(
          el.disabled || el.getAttribute("aria-disabled") === "true"
        ),
        visible: visible(el),
        identity: identity.slice(0, 120),
      });
    });
  }
  // Keep only visible, identified controls.
  return out.filter(e => e.visible && e.identity);
}
"""


def extract_interactive_elements(page: Page) -> list[dict[str, Any]]:
    """Return semantic descriptions of the interactive controls on the page."""
    try:
        elements = page.evaluate(_EXTRACTOR_JS)
    except Exception:
        elements = []
    # Attach a stable per-name index for disambiguation between duplicates.
    counter: dict[str, int] = {}
    for e in elements:
        key = f"{e['role']}:{e['accessible_name'] or e['text']}"
        counter[key] = counter.get(key, 0) + 1
        e["nth"] = counter[key]
    return elements


def extract_visible_text(page: Page) -> str:
    """Return the flattened visible text of the document body."""
    try:
        return page.locator("body").inner_text(timeout=2000)
    except Exception:
        return ""
