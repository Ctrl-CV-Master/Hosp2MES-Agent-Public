"""Production execution: advance the 7 canonical stages."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProductionOrder
from app.schemas import ExecutionStageOut, StageUpdate
from app.services.execution_engine import (
    apply_stage_action,
    ensure_stages,
    get_active_anomaly,
)

router = APIRouter(prefix="/api/orders", tags=["execution"])


@router.get("/{order_id}/stages", response_model=list[ExecutionStageOut])
def get_stages(order_id: int, db: Session = Depends(get_db)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    ensure_stages(order, db)
    return [s.to_dict() for s in order.stages]


@router.post("/{order_id}/stages/{stage_name}", response_model=ExecutionStageOut)
def update_stage(
    order_id: int,
    stage_name: str,
    payload: StageUpdate,
    db: Session = Depends(get_db),
):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    ensure_stages(order, db)

    # Demonstrate an injected stage failure anomaly.
    anomaly = get_active_anomaly(db, "execution")
    if anomaly and anomaly.type == "stage_failure" and payload.action == "complete":
        raise HTTPException(
            status_code=409,
            detail=f"Stage completion rejected (anomaly #{anomaly.id}: {anomaly.message})",
        )

    try:
        stage = apply_stage_action(
            order, stage_name, payload.action, payload.note, db
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.refresh(order)
    return stage.to_dict()
