"""CLI entry point.

Usage:
    python -m hosp2mes.run --task MES-DEMO-001
    python -m hosp2mes.run --task MES-DEMO-003 --inject-anomaly --server http://localhost:8000
    python -m hosp2mes.run --task MES-DEMO-001 --mode baseline
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from hosp2mes.agent.agent import Agent, TaskLoader
from hosp2mes.config import Config
from hosp2mes.observation.api_env import ApiEnv, BrowserEnv


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hosp2MES Agent runner")
    parser.add_argument("--task", required=True,
                        help="task id (e.g. MES-DEMO-001) or path to a .yaml task")
    parser.add_argument("--backend", default=None,
                        help="Mock MES backend base URL (default http://localhost:8000)")
    parser.add_argument("--server", default=None,
                        help="Backend URL to publish live trace for the Agent Monitor")
    parser.add_argument("--mode", default=None, choices=["hosp2mes", "baseline"])
    parser.add_argument("--llm", default=None, choices=["mock", "deepseek"])
    parser.add_argument("--inject-anomaly", action="store_true",
                        help="Inject a BOM save-failure anomaly to demonstrate recovery")
    parser.add_argument("--env", default="api", choices=["api", "browser"])
    args = parser.parse_args(argv)

    config = Config.load()
    if args.backend:
        config.backend_base_url = args.backend
    if args.server:
        config.publish_url = args.server
    if args.mode:
        config.agent_mode = args.mode
    if args.llm:
        config.llm_provider = args.llm

    root = _project_root()
    task_path = args.task
    if not os.path.exists(task_path):
        task_path = os.path.join(root, "benchmark", "tasks", f"{args.task}.yaml")
    if not os.path.exists(task_path):
        print(f"[error] task not found: {args.task}", file=sys.stderr)
        return 3

    task = TaskLoader.from_yaml(task_path)
    if args.inject_anomaly and not task.inject_anomaly:
        task.inject_anomaly = {
            "type": "save_failure", "target": "bom",
            "message": "CLI-injected BOM save failure for recovery demo",
        }

    if args.env == "browser":
        env = BrowserEnv(base_url="http://localhost:5173")
    else:
        env = ApiEnv(base_url=config.backend_base_url)

    agent = Agent(config, env, task)
    report, trace, memory = agent.run()

    results_dir = os.path.join(root, "benchmark", "results")
    os.makedirs(results_dir, exist_ok=True)
    trace.save(os.path.join(results_dir, f"{task.task_id}-trace.json"))
    with open(os.path.join(results_dir, f"{task.task_id}-report.json"),
              "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

    print("\n================ Hosp2MES Agent Result ================")
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print("======================================================\n")

    return 0 if report.task_success else 2


if __name__ == "__main__":
    raise SystemExit(main())
