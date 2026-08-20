"""End-to-end agent tests against a live Mock MES backend."""
from __future__ import annotations

import os
import time

from hosp2mes.agent.agent import Agent, TaskLoader
from hosp2mes.config import Config
from hosp2mes.observation.api_env import ApiEnv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TASKS_DIR = os.path.join(ROOT, "benchmark", "tasks")


def _run_task(task_id: str, base_url: str, mode: str = "hosp2mes"):
    cfg = Config(
        agent_mode=mode, llm_provider="mock",
        backend_base_url=base_url, publish_url=base_url,
    )
    env = ApiEnv(base_url=base_url)
    task = TaskLoader.from_yaml(os.path.join(TASKS_DIR, f"{task_id}.yaml"))
    agent = Agent(cfg, env, task)
    report, _trace, _mem = agent.run()
    return report


def test_e2e_task_001_material(live_server):
    report = _run_task("MES-DEMO-001", live_server)
    assert report.task_success, report.to_dict()
    assert report.subgoal_completion_rate == 1.0
    assert report.verifier_passed


def test_e2e_task_002_bom_order(live_server):
    report = _run_task("MES-DEMO-002", live_server)
    assert report.task_success, report.to_dict()
    assert report.verifier_passed


def test_e2e_task_003_hero_with_recovery(live_server):
    """Hero task: full workflow + injected BOM save-failure -> local recovery."""
    report = _run_task("MES-DEMO-003", live_server)
    assert report.task_success, report.to_dict()
    assert report.recovery_count >= 1, "hero task must exercise local recovery"
    assert report.verifier_passed


def test_e2e_baseline_mode_completes(live_server):
    """Baseline mode (no verifier gate / recovery) should still finish."""
    report = _run_task("MES-DEMO-001", live_server, mode="baseline")
    assert report.steps > 0


def test_launch_endpoint_streams_trace(live_server):
    """The Monitor's launch path: POST /api/agent/runs/launch then poll."""
    import httpx

    r = httpx.post(f"{live_server}/api/agent/runs/launch", json={
        "task_id": "MES-DEMO-001", "mode": "hosp2mes", "provider": "mock",
        "backend_url": live_server,
    })
    assert r.status_code == 202, r.text
    run_id = r.json()["id"]

    final = None
    for _ in range(60):
        r = httpx.get(f"{live_server}/api/agent/runs/{run_id}", timeout=5)
        final = r.json()
        if final["status"] == "DONE":
            break
        time.sleep(0.5)

    assert final["status"] == "DONE"
    assert final["success"] is True
    assert len(final["trace"]) > 0
