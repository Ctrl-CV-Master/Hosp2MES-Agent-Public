"""Pydantic request/response schemas for the Mock MES API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ----------------------------- Materials -----------------------------
class MaterialCreate(BaseModel):
    material_code: str
    material_name: str
    material_type: str = "raw"
    unit: str = "kg"
    specification: str = ""
    status: str = "ACTIVE"


class MaterialUpdate(BaseModel):
    material_name: str | None = None
    material_type: str | None = None
    unit: str | None = None
    specification: str | None = None
    status: str | None = None


class MaterialOut(BaseModel):
    id: int
    material_code: str
    material_name: str
    material_type: str
    unit: str
    specification: str
    status: str
    created_at: datetime | None = None


# ------------------------------- BOM --------------------------------
class BOMItemIn(BaseModel):
    material_code: str
    quantity: float


class BOMCreate(BaseModel):
    bom_code: str
    product: str
    version: str = "1.0"
    route: str = ""
    status: str = "DRAFT"
    materials: list[BOMItemIn] = Field(default_factory=list)


class BOMItemOut(BaseModel):
    id: int
    material_code: str
    quantity: float


class BOMOut(BaseModel):
    id: int
    bom_code: str
    product: str
    version: str
    route: str
    status: str
    created_at: datetime | None = None
    materials: list[BOMItemOut] = Field(default_factory=list)


# --------------------------- Production Order ------------------------
class ProductionOrderCreate(BaseModel):
    order_code: str
    product: str
    batch: str = ""
    quantity: int = 1


class ProductionOrderOut(BaseModel):
    id: int
    order_code: str
    product: str
    batch: str
    quantity: int
    status: str
    created_at: datetime | None = None
    stages: list["ExecutionStageOut"] = Field(default_factory=list)


class ExecutionStageOut(BaseModel):
    id: int
    order_id: int
    stage_name: str
    stage_label: str
    stage_status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    note: str = ""


class StageUpdate(BaseModel):
    action: str  # "start" | "complete" | "fail"
    note: str = ""


# ----------------------------- Anomaly ------------------------------
class AnomalyCreate(BaseModel):
    type: str
    target: str = "bom"
    message: str = ""


class AnomalyOut(BaseModel):
    id: int
    type: str
    target: str
    message: str
    active: bool
    created_at: datetime | None = None


# ----------------------------- Dashboard ----------------------------
class DashboardSummary(BaseModel):
    today_tasks: int
    completed: int
    in_progress: int
    anomalies: int
    completion_rate: float
    recent_orders: list[ProductionOrderOut] = Field(default_factory=list)


# ----------------------------- Generic ------------------------------
class Message(BaseModel):
    detail: str


ProductionOrderOut.model_rebuild()
