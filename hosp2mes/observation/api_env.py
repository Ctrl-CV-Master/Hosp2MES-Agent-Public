"""Environment abstraction for the Mock MES.

The agent never talks to the MES database directly. It interacts with the MES
through an *environment* that exposes:
  - ``observe()``  -> the agent's current observation (page + data)
  - high level operations (create_material, complete_stage, ...) that are the
    concrete realization of the abstract GUI action vocabulary
  - ``system_state(...)`` -> the business state used by the Evidence Verifier

Two concrete environments are provided:
  * ``ApiEnv``   - drives the live Mock MES over its REST API (default, fully
                  runnable and testable without a browser).
  * ``BrowserEnv`` - a Playwright-backed environment (documented extension point;
                  not required for the public demo to run).

This mirrors the Observation/Action abstraction used by projects such as
BrowserGym, but targets a REST MES instead of a raw DOM. The architecture keeps
a clean seam so a browser/DOM observation backend can be dropped in later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class Observation:
    page: str
    data: dict[str, Any] = field(default_factory=dict)
    available_actions: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class ActionResult:
    ok: bool
    action: str = ""
    observation: Observation | None = None
    detail: str = ""
    http_status: int | None = None
    recoverable: bool = False     # True when failure is due to an injected anomaly
    evidence: dict = field(default_factory=dict)


class ApiEnv:
    """Live Mock MES environment driven through its REST API."""

    def __init__(self, base_url: str = "http://localhost:8000", client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.current_page = "dashboard"

    # ---- low level -------------------------------------------------------
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=30)
        return self._client

    def _get(self, path: str) -> Any:
        r = self.client.get(path)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: dict) -> httpx.Response:
        return self.client.post(path, json=json)

    # ---- observation -----------------------------------------------------
    def observe(self) -> Observation:
        data: dict[str, Any] = {}
        actions: list[str] = ["navigate"]
        if self.current_page == "materials":
            data["materials"] = self._get("/api/materials")
            actions += ["create_material", "input", "click", "verify"]
        elif self.current_page == "boms":
            data["boms"] = self._get("/api/boms")
            actions += ["create_bom", "add_material", "click", "verify"]
        elif self.current_page == "orders":
            data["orders"] = self._get("/api/orders")
            actions += ["create_order", "start_order", "click", "verify"]
        elif self.current_page == "execution":
            data["orders"] = self._get("/api/orders")
            actions += ["complete_stage", "click", "verify"]
        return Observation(page=self.current_page, data=data, available_actions=actions)

    def navigate(self, page: str) -> ActionResult:
        self.current_page = page
        return ActionResult(ok=True, action=f"navigate:{page}", observation=self.observe())

    # ---- materials -------------------------------------------------------
    def create_material(self, code: str, name: str, mtype: str = "raw",
                        unit: str = "kg", spec: str = "") -> ActionResult:
        r = self._post("/api/materials", json={
            "material_code": code, "material_name": name,
            "material_type": mtype, "unit": unit, "specification": spec,
        })
        if r.status_code >= 400:
            return self._err("create_material", r)
        return ActionResult(ok=True, action="click:save_material",
                            detail=f"material {code} created",
                            evidence={"material_code": code})

    def get_material(self, code: str) -> dict | None:
        for m in self._get("/api/materials"):
            if m["material_code"] == code:
                return m
        return None

    # ---- BOM -------------------------------------------------------------
    def create_bom(self, bom_code: str, product: str, materials: list[dict],
                   version: str = "1.0") -> ActionResult:
        r = self._post("/api/boms", json={
            "bom_code": bom_code, "product": product, "version": version,
            "materials": materials,
        })
        if r.status_code >= 400:
            return self._err("create_bom", r)
        return ActionResult(ok=True, action="click:save_bom",
                            detail=f"bom {bom_code} created",
                            evidence={"bom_code": bom_code, "product": product})

    def get_bom_for_product(self, product: str) -> dict | None:
        for b in self._get("/api/boms"):
            if b["product"] == product:
                return b
        return None

    def get_bom(self, bom_code: str) -> dict | None:
        for b in self._get("/api/boms"):
            if b["bom_code"] == bom_code:
                return b
        return None

    # ---- production order ------------------------------------------------
    def create_order(self, order_code: str, product: str, batch: str,
                     quantity: int) -> ActionResult:
        r = self._post("/api/orders", json={
            "order_code": order_code, "product": product,
            "batch": batch, "quantity": quantity,
        })
        if r.status_code >= 400:
            return self._err("create_order", r)
        return ActionResult(ok=True, action="click:save_order",
                            detail=f"order {order_code} created",
                            evidence={"order_code": order_code})

    def start_order(self, product: str) -> ActionResult:
        order = self._order_for_product(product)
        if not order:
            return ActionResult(ok=False, action="start_order",
                                detail="no order found for product")
        r = self._post(f"/api/orders/{order['id']}/start", json={})
        if r.status_code >= 400:
            return self._err("start_order", r)
        return ActionResult(ok=True, action="click:start_order",
                            detail=f"order {order['order_code']} started",
                            evidence={"order_id": order["id"]})

    def complete_stage(self, product: str, stage: str) -> ActionResult:
        order = self._order_for_product(product)
        if not order:
            return ActionResult(ok=False, action="complete_stage",
                                detail="no order found for product")
        r = self._post(f"/api/orders/{order['id']}/stages/{stage}",
                       json={"action": "complete"})
        if r.status_code >= 400:
            return self._err("complete_stage", r)
        return ActionResult(ok=True, action=f"click:complete_{stage}",
                            detail=f"stage {stage} completed",
                            evidence={"stage": stage, "order_id": order["id"]})

    def get_order(self, order_code: str) -> dict | None:
        for o in self._get("/api/orders"):
            if o["order_code"] == order_code:
                return o
        return None

    def get_order_for_product(self, product: str) -> dict | None:
        return self._order_for_product(product)

    def _order_for_product(self, product: str) -> dict | None:
        for o in self._get("/api/orders"):
            if o["product"] == product:
                return o
        return None

    # ---- anomalies (for recovery demos) ---------------------------------
    def inject_anomaly(self, atype: str, target: str, message: str = "") -> int:
        r = self._post("/api/anomalies", json={
            "type": atype, "target": target, "message": message})
        r.raise_for_status()
        return r.json()["id"]

    def resolve_anomaly(self, anomaly_id: int) -> bool:
        r = self._post(f"/api/anomalies/{anomaly_id}/resolve", json={})
        return r.status_code < 400

    def active_anomalies(self, target: str) -> list[dict]:
        out = []
        for a in self._get("/api/anomalies"):
            if a["active"] and (a["target"] == target or a["target"] == "global"):
                out.append(a)
        return out

    # ---- evidence (for the Verifier) ------------------------------------
    def system_state(self, product: str | None = None,
                     material_code: str | None = None) -> dict:
        state: dict[str, Any] = {}
        if material_code:
            state["material_exists"] = self.get_material(material_code) is not None
        if product:
            bom = self.get_bom_for_product(product)
            state["bom_exists"] = bom is not None
            order = self._order_for_product(product)
            if order is None:
                state["production_order_status"] = None
                state["storage_status"] = "NOT_STORED"
            else:
                state["production_order_status"] = order["status"]
                stored = any(
                    s["stage_name"] == "storage" and s["stage_status"] == "COMPLETED"
                    for s in order.get("stages", [])
                )
                state["storage_status"] = "STORED" if stored else "NOT_STORED"
        return state

    # ---- helpers --------------------------------------------------------
    def _err(self, action: str, resp: httpx.Response) -> ActionResult:
        try:
            body = resp.json()
            detail = body.get("detail", resp.text)
        except Exception:
            detail = resp.text
        recoverable = "anomaly" in str(detail).lower() or resp.status_code == 409
        return ActionResult(ok=False, action=action, detail=detail,
                            http_status=resp.status_code, recoverable=recoverable)

    def reset(self) -> None:
        self.current_page = "dashboard"


class BrowserEnv:
    """Playwright-backed environment (extension point).

    The public demo targets the REST ``ApiEnv`` so it runs without a browser.
    This class documents where a DOM/screenshot observation backend would plug
    in: implement ``observe`` to return a screenshot+DOM observation and
    implement the GUI action verbs with Playwright. The agent loop, planner,
    memory, verifier and recovery are environment-agnostic and work unchanged.
    """

    def __init__(self, base_url: str = "http://localhost:5173"):
        self.base_url = base_url
        raise NotImplementedError(
            "BrowserEnv is a documented extension point. The public demo uses "
            "ApiEnv (REST). Implement observe()/GUI actions with Playwright here."
        )
