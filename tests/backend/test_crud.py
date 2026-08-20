"""Backend CRUD + dashboard tests against a fresh seeded database."""
from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_materials_crud(client):
    # seeded data present
    r = client.get("/api/materials")
    assert r.status_code == 200
    assert any(m["material_code"] == "MAT-KCL" for m in r.json())

    # create
    r = client.post("/api/materials", json={
        "material_code": "MAT-TEST-1", "material_name": "测试物料",
        "material_type": "raw", "unit": "kg", "specification": "x",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    # duplicate rejected
    r = client.post("/api/materials", json={
        "material_code": "MAT-TEST-1", "material_name": "测试物料",
    })
    assert r.status_code == 409

    # get / update / delete
    r = client.get(f"/api/materials/{mid}")
    assert r.status_code == 200
    r = client.put(f"/api/materials/{mid}", json={"status": "DISABLED"})
    assert r.json()["status"] == "DISABLED"
    r = client.delete(f"/api/materials/{mid}")
    assert r.status_code == 200
    r = client.get(f"/api/materials/{mid}")
    assert r.status_code == 404


def test_boms_crud(client):
    r = client.get("/api/boms")
    assert r.status_code == 200
    assert any(b["bom_code"] == "BOM-KCL-001" for b in r.json())

    r = client.post("/api/boms", json={
        "bom_code": "BOM-TEST-1", "product": "DEMO-TEST", "version": "1.0",
        "route": "weighing>storage", "status": "ACTIVE",
        "materials": [{"material_code": "MAT-KCL", "quantity": 1.0}],
    })
    assert r.status_code == 201, r.text
    bid = r.json()["id"]

    # add / remove a BOM item
    r = client.post(f"/api/boms/{bid}/materials",
                    json={"material_code": "MAT-WATER", "quantity": 10.0})
    assert r.status_code == 200
    item_id = [i["id"] for i in r.json()["materials"]
               if i["material_code"] == "MAT-WATER"][0]
    r = client.delete(f"/api/boms/{bid}/materials/{item_id}")
    assert r.status_code == 200
    assert all(i["material_code"] != "MAT-WATER" for i in r.json()["materials"])


def test_orders_and_execution(client):
    r = client.post("/api/orders", json={
        "order_code": "ORD-TEST-1", "product": "DEMO-TEST",
        "batch": "B1", "quantity": 5,
    })
    assert r.status_code == 201, r.text
    oid = r.json()["id"]

    r = client.post(f"/api/orders/{oid}/start")
    assert r.status_code == 200

    # complete the canonical 7 stages
    for stage in ["weighing", "dissolution", "filtration",
                  "filling", "labeling", "packaging", "storage"]:
        r = client.post(f"/api/orders/{oid}/stages/{stage}",
                        json={"action": "complete"})
        assert r.status_code == 200, r.text

    r = client.get(f"/api/orders/{oid}")
    assert r.json()["status"] == "COMPLETED"
    stored = any(s["stage_name"] == "storage" and s["stage_status"] == "COMPLETED"
                 for s in r.json()["stages"])
    assert stored


def test_anomalies(client):
    r = client.post("/api/anomalies", json={
        "type": "save_failure", "target": "bom", "message": "demo",
    })
    assert r.status_code == 201
    aid = r.json()["id"]

    r = client.get("/api/anomalies")
    assert any(a["id"] == aid and a["active"] for a in r.json())

    # A BOM save must now be rejected until the anomaly is resolved.
    r = client.post("/api/boms", json={
        "bom_code": "BOM-FAULT", "product": "DEMO-FAULT", "version": "1.0",
        "route": "storage", "status": "ACTIVE", "materials": [],
    })
    assert r.status_code == 409

    r = client.post(f"/api/anomalies/{aid}/resolve")
    assert r.status_code == 200
    r = client.post("/api/boms", json={
        "bom_code": "BOM-FAULT", "product": "DEMO-FAULT", "version": "1.0",
        "route": "storage", "status": "ACTIVE", "materials": [],
    })
    assert r.status_code == 201


def test_dashboard(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert "today_tasks" in d and "completion_rate" in d
