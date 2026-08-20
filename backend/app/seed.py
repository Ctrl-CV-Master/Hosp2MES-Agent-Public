"""Synthetic seed data for the Mock MES demo.

IMPORTANT: Every product, batch and record below is fictional demonstration
data. No real hospital / MES data is used anywhere in this repository.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import BOM, BOMItem, Material, ProductionOrder

SEED_MATERIALS = [
    ("MAT-KCL", "氯化钾原料", "raw", "kg", "USP grade, 99.0%", "ACTIVE"),
    ("MAT-GLU", "葡萄糖原料", "raw", "kg", "Anhydrous, BP", "ACTIVE"),
    ("MAT-NACL", "氯化钠原料", "raw", "kg", "Injection grade", "ACTIVE"),
    ("MAT-WATER", "注射用水", "solvent", "L", "WFI", "ACTIVE"),
    ("MAT-PACK", "成品包装瓶", "packaging", "pcs", "250ml amber", "ACTIVE"),
    ("MAT-LABEL", "标签纸", "packaging", "roll", "thermal", "ACTIVE"),
]

SEED_BOMS = [
    (
        "BOM-KCL-001",
        "DEMO-KCL-SOLUTION",
        "1.0",
        "weighing>dissolution>filtration>filling>labeling>packaging>storage",
        [
            ("MAT-KCL", 1.5),
            ("MAT-WATER", 100.0),
            ("MAT-PACK", 100.0),
            ("MAT-LABEL", 1.0),
        ],
    ),
    (
        "BOM-GLU-001",
        "DEMO-GLUCOSE-SOLUTION",
        "1.0",
        "weighing>dissolution>filtration>filling>labeling>packaging>storage",
        [
            ("MAT-GLU", 5.0),
            ("MAT-WATER", 100.0),
            ("MAT-PACK", 100.0),
            ("MAT-LABEL", 1.0),
        ],
    ),
]

SEED_ORDERS = [
    ("ORD-2026-0001", "DEMO-GLUCOSE-SOLUTION", "B20260801", 100),
    ("ORD-2026-0002", "DEMO-ELECTROLYTE-SOLUTION", "B20260802", 50),
]


def seed(db: Session) -> None:
    if db.query(Material).first():
        return  # already seeded

    for code, name, mtype, unit, spec, status in SEED_MATERIALS:
        db.add(
            Material(
                material_code=code,
                material_name=name,
                material_type=mtype,
                unit=unit,
                specification=spec,
                status=status,
            )
        )

    for bom_code, product, version, route, items in SEED_BOMS:
        bom = BOM(
            bom_code=bom_code,
            product=product,
            version=version,
            route=route,
            status="ACTIVE",
        )
        for mcode, qty in items:
            bom.items.append(BOMItem(material_code=mcode, quantity=qty))
        db.add(bom)

    for order_code, product, batch, qty in SEED_ORDERS:
        db.add(
            ProductionOrder(
                order_code=order_code,
                product=product,
                batch=batch,
                quantity=qty,
                status="NOT_STARTED",
            )
        )

    db.commit()
