"""BOM management with materials + anomaly-aware save."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BOM, BOMItem
from app.schemas import BOMCreate, BOMItemIn, BOMOut
from app.services.execution_engine import get_active_anomaly

router = APIRouter(prefix="/api/boms", tags=["boms"])


@router.get("", response_model=list[BOMOut])
def list_boms(db: Session = Depends(get_db), product: str | None = None):
    query = db.query(BOM)
    if product:
        query = query.filter(BOM.product.contains(product))
    return [b.to_dict() for b in query.order_by(BOM.id.desc()).all()]


@router.post("", response_model=BOMOut, status_code=201)
def create_bom(payload: BOMCreate, db: Session = Depends(get_db)):
    # Demonstrate injected "BOM save failure" anomaly for Agent recovery.
    anomaly = get_active_anomaly(db, "bom")
    if anomaly and anomaly.type == "save_failure":
        raise HTTPException(
            status_code=409,
            detail=f"BOM save rejected (anomaly #{anomaly.id}: {anomaly.message})",
        )

    if db.query(BOM).filter(BOM.bom_code == payload.bom_code).first():
        raise HTTPException(status_code=409, detail="bom_code already exists")

    bom = BOM(
        bom_code=payload.bom_code,
        product=payload.product,
        version=payload.version,
        route=payload.route,
        status=payload.status,
    )
    for item in payload.materials:
        bom.items.append(BOMItem(**item.model_dump()))
    db.add(bom)
    db.commit()
    db.refresh(bom)
    return bom.to_dict()


@router.get("/{bom_id}", response_model=BOMOut)
def get_bom(bom_id: int, db: Session = Depends(get_db)):
    bom = db.get(BOM, bom_id)
    if not bom:
        raise HTTPException(status_code=404, detail="bom not found")
    return bom.to_dict()


@router.post("/{bom_id}/materials", response_model=BOMOut)
def add_material(bom_id: int, item: BOMItemIn, db: Session = Depends(get_db)):
    bom = db.get(BOM, bom_id)
    if not bom:
        raise HTTPException(status_code=404, detail="bom not found")
    bom.items.append(BOMItem(**item.model_dump()))
    db.commit()
    db.refresh(bom)
    return bom.to_dict()


@router.delete("/{bom_id}/materials/{item_id}", response_model=BOMOut)
def remove_material(bom_id: int, item_id: int, db: Session = Depends(get_db)):
    bom = db.get(BOM, bom_id)
    if not bom:
        raise HTTPException(status_code=404, detail="bom not found")
    item = db.get(BOMItem, item_id)
    if not item or item.bom_id != bom.id:
        raise HTTPException(status_code=404, detail="bom item not found")
    db.delete(item)
    db.commit()
    db.refresh(bom)
    return bom.to_dict()
