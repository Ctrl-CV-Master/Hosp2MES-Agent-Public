"""Materials master-file CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Material
from app.schemas import MaterialCreate, MaterialOut, MaterialUpdate, Message

router = APIRouter(prefix="/api/materials", tags=["materials"])


@router.get("", response_model=list[MaterialOut])
def list_materials(db: Session = Depends(get_db), q: str | None = None):
    query = db.query(Material)
    if q:
        query = query.filter(Material.material_name.contains(q))
    return [m.to_dict() for m in query.order_by(Material.id.desc()).all()]


@router.post("", response_model=MaterialOut, status_code=201)
def create_material(payload: MaterialCreate, db: Session = Depends(get_db)):
    if db.query(Material).filter(Material.material_code == payload.material_code).first():
        raise HTTPException(status_code=409, detail="material_code already exists")
    m = Material(**payload.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m.to_dict()


@router.get("/{material_id}", response_model=MaterialOut)
def get_material(material_id: int, db: Session = Depends(get_db)):
    m = db.get(Material, material_id)
    if not m:
        raise HTTPException(status_code=404, detail="material not found")
    return m.to_dict()


@router.put("/{material_id}", response_model=MaterialOut)
def update_material(
    material_id: int, payload: MaterialUpdate, db: Session = Depends(get_db)
):
    m = db.get(Material, material_id)
    if not m:
        raise HTTPException(status_code=404, detail="material not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m.to_dict()


@router.delete("/{material_id}", response_model=Message)
def delete_material(material_id: int, db: Session = Depends(get_db)):
    m = db.get(Material, material_id)
    if not m:
        raise HTTPException(status_code=404, detail="material not found")
    db.delete(m)
    db.commit()
    return Message(detail="deleted")
