"""FastAPI entrypoint for the Mock MES backend."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
import app.database as _dbmod
from app.routers import agent, anomalies, boms, dashboard, execution, materials, orders
from app.seed import seed

DESCRIPTION = (
    "Mock Manufacturing Execution System (MES) for the Hosp2MES-Agent demo.\n\n"
    "**All products, batches and manufacturing records are synthetic demonstration "
    "data.** No real hospital / MES data is included."
)

app = FastAPI(
    title="Hosp2MES Mock MES",
    description=DESCRIPTION,
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(materials.router)
app.include_router(boms.router)
app.include_router(orders.router)
app.include_router(execution.router)
app.include_router(anomalies.router)
app.include_router(agent.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # Reference the *live* SessionLocal so a runtime configure_engine() (used by
    # the benchmark harness and tests for DB isolation) is honoured here too.
    db = _dbmod.SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


@app.get("/")
def root():
    return {"service": "Hosp2MES Mock MES", "docs": "/docs", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}
