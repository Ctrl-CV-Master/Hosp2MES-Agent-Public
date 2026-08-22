"""CLI entry point.

Usage:
    # deterministic test / CI backend (default)
    python -m hosp2mes.run --task MES-DEMO-001 --env api
    # real browser GUI execution — deterministic skill baseline
    python -m hosp2mes.run --task MES-DEMO-GUI-001 --env browser --headless false
    # real browser GUI execution — one-action-per-step policy agent
    python -m hosp2mes.run --task MES-DEMO-GUI-001 --env browser --agent hosp2mes
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from hosp2mes.agent.agent import Agent, TaskLoader
from hosp2mes.agent.browser_agent import BrowserAgent
from hosp2mes.config import Config
from hosp2mes.observation.api_env import ApiEnv
from hosp2mes.observation.browser_env import BrowserEnv


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hosp2MES Agent runner")
    parser.add_argument("--task", required=True,
                        help="task id (e.g. MES-DEMO-001) or path to a .yaml task")
    parser.add_argument("--backend", default=None,
                        help="Mock MES backend base URL (default http://localhost:8000)")
    parser.add_argument("--frontend", default=None,
                        help="Vue Mock MES frontend URL (default http://localhost:5173)")
    parser.add_argument("--server", default=None,
                        help="Backend URL to publish live trace for the Agent Monitor")
    parser.add_argument("--mode", default=None, choices=["hosp2mes", "baseline"])
    parser.add_argument("--llm", default=None, choices=["mock", "deepseek"])
    parser.add_argument("--inject-anomaly", action="store_true",
                        help="Inject a BOM save-failure anomaly to demonstrate recovery")
    parser.add_argument("--env", default="api", choices=["api", "browser"],
                        help="execution environment: api (REST, deterministic) or "
                             "browser (real GUI via Playwright)")
    parser.add_argument("--agent", default="skill", choices=["skill", "hosp2mes", "s3"],
                        help="browser-mode agent: skill (deterministic baseline), "
                             "hosp2mes (one-action-per-step policy), s3 (Agent S3)")
    parser.add_argument("--headless", default=None, metavar="true|false",
                        help="browser mode only: run Chromium headless (default true)")
    args = parser.parse_args(argv)

    config = Config.load()
    if args.backend:
        config.backend_base_url = args.backend
    if args.frontend:
        config.frontend_url = args.frontend
    if args.server:
        config.publish_url = args.server
    if args.mode:
        config.agent_mode = args.mode
    if args.llm:
        config.llm_provider = args.llm
    if args.env == "browser":
        config.headless = _parse_bool(args.headless, default=config.headless)

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
        env = BrowserEnv(
            base_url=config.frontend_url,
            backend_url=config.backend_base_url,
            headless=config.headless,
            artifacts_dir=None,  # screenshots land in EvidenceWriter's run dir
        )
        if args.agent == "hosp2mes":
            from hosp2mes.agents.hosp2mes_agent import Hosp2MESAgent

            agent = Hosp2MESAgent(config, env, task)
        elif args.agent == "s3":
            from hosp2mes.agents.agent_s3_adapter import AgentS3Adapter

            adapter = AgentS3Adapter(config)
            # Agent S3 runs on its own OS-level loop; here we surface the
            # adapter explicitly rather than driving our BrowserEnv loop.
            print("[s3] Agent S3 adapter selected. It requires gui-agents + an "
                  "LLM API key + a UI-TARS grounding model endpoint to actually "
                  "predict actions. See hosp2mes/agents/agent_s3_adapter.py.")
            if not adapter.is_installed():
                print("[s3] gui-agents is not installed; cannot run Agent S3.", file=sys.stderr)
                return 4
            print("[s3] gui-agents is installed, but a real run still needs "
                  "worker_engine_params + grounding_engine_params.")
            return 4
        else:
            agent = BrowserAgent(config, env, task)
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
    if args.env == "browser":
        print(f"[browser] run_id={agent.run_id}")
        print(f"[browser] evidence_dir=artifacts/runs/{agent.run_id}")
        print(f"[browser] gui_steps={agent.gui_steps} "
              f"failed_subgoal={agent.failed_subgoal or '-'} "
              f"failure_reason={agent.failure_reason or '-'}")
    print("======================================================\n")

    return 0 if report.task_success else 2


if __name__ == "__main__":
    raise SystemExit(main())
