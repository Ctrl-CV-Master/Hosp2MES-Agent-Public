"""Production order creation and status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProductionOrder
from app.schemas import ProductionOrderCreate, ProductionOrderOut
from app.services.execution_engine import get_active_anomaly

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=list[ProductionOrderOut])
def list_orders(db: Session = Depends(get_db), product: str | None = None):
    query = db.query(ProductionOrder)
    if product:
        query = query.filter(ProductionOrder.product.contains(product))
    return [o.to_dict() for o in query.order_by(ProductionOrder.id.desc()).all()]


@router.post("", response_model=ProductionOrderOut, status_code=201)
def create_order(payload: ProductionOrderCreate, db: Session = Depends(get_db)):
    anomaly = get_active_anomaly(db, "order")
    if anomaly and anomaly.type == "save_failure":
        raise HTTPException(
            status_code=409,
            detail=f"Order save rejected (anomaly #{anomaly.id}: {anomaly.message})",
        )
    if db.query(ProductionOrder).filter(
        ProductionOrder.order_code == payload.order_code
    ).first():
        raise HTTPException(status_code=409, detail="order_code already exists")

    order = ProductionOrder(**payload.model_dump())
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("/{order_id}", response_model=ProductionOrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    return order.to_dict()


@router.post("/{order_id}/start", response_model=ProductionOrderOut)
def start_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(ProductionOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    from app.services.execution_engine import ensure_stages

    order.status = "IN_PROGRESS"
    ensure_stages(order, db)
    db.commit()
    db.refresh(order)
    return order.to_dict()
