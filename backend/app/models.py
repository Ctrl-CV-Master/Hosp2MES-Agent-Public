"""SQLAlchemy ORM models for the Mock MES.

All data here is SYNTHETIC demonstration data. No real hospital / MES data.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Canonical production execution stages (order matters).
PRODUCTION_STAGES = [
    "weighing",      # 称量
    "dissolution",   # 溶解
    "filtration",    # 过滤
    "filling",       # 分装
    "labeling",      # 贴签
    "packaging",     # 包装
    "storage",       # 入库
]

STAGE_LABELS_ZH = {
    "weighing": "称量",
    "dissolution": "溶解",
    "filtration": "过滤",
    "filling": "分装",
    "labeling": "贴签",
    "packaging": "包装",
    "storage": "入库",
}


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    material_name: Mapped[str] = mapped_column(String(128))
    material_type: Mapped[str] = mapped_column(String(64), default="raw")
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    specification: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "material_code": self.material_code,
            "material_name": self.material_name,
            "material_type": self.material_type,
            "unit": self.unit,
            "specification": self.specification,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BOM(Base):
    __tablename__ = "boms"
    __table_args__ = (UniqueConstraint("bom_code", name="uq_bom_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bom_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(16), default="1.0")
    route: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    items: Mapped[list["BOMItem"]] = relationship(
        back_populates="bom", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bom_code": self.bom_code,
            "product": self.product,
            "version": self.version,
            "route": self.route,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "materials": [i.to_dict() for i in self.items],
        }


class BOMItem(Base):
    __tablename__ = "bom_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("boms.id", ondelete="CASCADE"))
    material_code: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[float] = mapped_column(default=0.0)

    bom: Mapped["BOM"] = relationship(back_populates="items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "material_code": self.material_code,
            "quantity": self.quantity,
        }


class ProductionOrder(Base):
    __tablename__ = "production_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product: Mapped[str] = mapped_column(String(128), index=True)
    batch: Mapped[str] = mapped_column(String(64), default="")
    quantity: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    stages: Mapped[list["ExecutionStage"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_code": self.order_code,
            "product": self.product,
            "batch": self.batch,
            "quantity": self.quantity,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "stages": [s.to_dict() for s in self.stages],
        }


class ExecutionStage(Base):
    __tablename__ = "execution_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id", ondelete="CASCADE")
    )
    stage_name: Mapped[str] = mapped_column(String(64))
    stage_status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

    order: Mapped["ProductionOrder"] = relationship(back_populates="stages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "stage_name": self.stage_name,
            "stage_label": STAGE_LABELS_ZH.get(self.stage_name, self.stage_name),
            "stage_status": self.stage_status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "note": self.note,
        }


class Anomaly(Base):
    """Injectable anomaly used to demonstrate Agent failure / recovery."""

    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(64))  # save_failure | data_missing | ...
    target: Mapped[str] = mapped_column(String(64), default="bom")  # module scope
    message: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "target": self.target,
            "message": self.message,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentRun(Base):
    """Persisted Agent trajectory for the Monitor / evaluation."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    goal: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(32), default="hosp2mes")
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    current_subgoal: Mapped[str] = mapped_column(Text, default="")
    step_count: Mapped[int] = mapped_column(default=0)
    recovery_count: Mapped[int] = mapped_column(default=0)
    success: Mapped[bool | None] = mapped_column(default=None)
    final_verification: Mapped[str] = mapped_column(Text, default="")
    trace: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        import json

        return {
            "id": self.id,
            "task_id": self.task_id,
            "goal": self.goal,
            "mode": self.mode,
            "status": self.status,
            "current_subgoal": self.current_subgoal,
            "step_count": self.step_count,
            "recovery_count": self.recovery_count,
            "success": self.success,
            "final_verification": self.final_verification,
            "trace": json.loads(self.trace or "[]"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
