"""Anomaly injection / resolution for Agent recovery demos."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Anomaly
from app.schemas import AnomalyCreate, AnomalyOut, Message

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("", response_model=list[AnomalyOut])
def list_anomalies(db: Session = Depends(get_db)):
    return [a.to_dict() for a in db.query(Anomaly).order_by(Anomaly.id.desc()).all()]


@router.post("", response_model=AnomalyOut, status_code=201)
def create_anomaly(payload: AnomalyCreate, db: Session = Depends(get_db)):
    a = Anomaly(**payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.post("/{anomaly_id}/resolve", response_model=AnomalyOut)
def resolve_anomaly(anomaly_id: int, db: Session = Depends(get_db)):
    a = db.get(Anomaly, anomaly_id)
    if not a:
        raise HTTPException(status_code=404, detail="anomaly not found")
    a.active = False
    db.commit()
    db.refresh(a)
    return a
