"""Business logic for production execution and anomaly handling."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    PRODUCTION_STAGES,
    Anomaly,
    ExecutionStage,
    ProductionOrder,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_active_anomaly(db: Session, target: str) -> Anomaly | None:
    """Return the first *active* anomaly scoped to ``target`` (or global)."""
    return (
        db.query(Anomaly)
        .filter(Anomaly.active.is_(True))
        .filter((Anomaly.target == target) | (Anomaly.target == "global"))
        .order_by(Anomaly.id.desc())
        .first()
    )


def ensure_stages(order: ProductionOrder, db: Session) -> None:
    """Create the 7 canonical execution stages if not present yet."""
    if order.stages:
        return
    for name in PRODUCTION_STAGES:
        db.add(ExecutionStage(order_id=order.id, stage_name=name))
    db.commit()
    db.refresh(order)


def all_stages_completed(order: ProductionOrder) -> bool:
    return bool(order.stages) and all(s.stage_status == "COMPLETED" for s in order.stages)


def storage_stored(order: ProductionOrder) -> bool:
    for s in order.stages:
        if s.stage_name == "storage" and s.stage_status == "COMPLETED":
            return True
    return False


def apply_stage_action(
    order: ProductionOrder, stage_name: str, action: str, note: str, db: Session
) -> ExecutionStage:
    """Apply start/complete/fail to a single stage and roll up order status."""
    stage = next((s for s in order.stages if s.stage_name == stage_name), None)
    if stage is None:
        raise ValueError(f"unknown stage: {stage_name}")

    now = _utcnow()
    if action == "start":
        stage.stage_status = "IN_PROGRESS"
        stage.started_at = now
    elif action == "complete":
        stage.stage_status = "COMPLETED"
        stage.completed_at = now
    elif action == "fail":
        stage.stage_status = "FAILED"
        stage.note = note
    else:
        raise ValueError(f"unknown action: {action}")

    # Roll up order status
    if any(s.stage_status == "FAILED" for s in order.stages):
        order.status = "FAILED"
    elif all_stages_completed(order):
        order.status = "COMPLETED"
    elif any(s.stage_status in ("IN_PROGRESS", "COMPLETED") for s in order.stages):
        order.status = "IN_PROGRESS"
    else:
        order.status = "NOT_STARTED"

    db.commit()
    db.refresh(stage)
    return stage
