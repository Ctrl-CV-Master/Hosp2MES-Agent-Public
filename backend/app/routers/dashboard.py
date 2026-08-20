"""Dashboard summary endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Anomaly, ProductionOrder
from app.schemas import DashboardSummary

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard", response_model=DashboardSummary)
def dashboard(db: Session = Depends(get_db)):
    orders = db.query(ProductionOrder).all()
    completed = sum(1 for o in orders if o.status == "COMPLETED")
    in_progress = sum(1 for o in orders if o.status == "IN_PROGRESS")
    anomalies = db.query(Anomaly).filter(Anomaly.active.is_(True)).count()
    total = len(orders) or 1
    rate = round(completed / total * 100, 1)

    recent = (
        db.query(ProductionOrder).order_by(ProductionOrder.id.desc()).limit(5).all()
    )
    return DashboardSummary(
        # recent_orders expects Pydantic models; pass ORM objects as dicts.
        recent_orders=[o.to_dict() for o in recent],
        today_tasks=len(orders),
        completed=completed,
        in_progress=in_progress,
        anomalies=anomalies,
        completion_rate=rate,
    )
