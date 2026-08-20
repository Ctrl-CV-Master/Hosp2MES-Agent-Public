# Third-Party Notices

Hosp2MES-Agent is an original implementation. No third-party source code is
vendored or copied into this repository. The architecture and engineering
approach were **informed by** the publicly documented designs of the following
open-source projects, which we acknowledge and recommend for reference:

| Project | License | How it informed Hosp2MES |
| --- | --- | --- |
| [Agent S3](https://github.com/") (GUI agent baseline concept) | Refer to upstream | Used as the conceptual **baseline GUI agent**; we keep the "baseline vs Hosp2MES" comparison mode. Our planner/memory/verifier/recovery are original extensions. |
| [Browser Use](https://github.com/browser-use/browser-use) | MIT | Borrowed the *session / tool abstraction / agent–environment interaction* shape (we target a REST MES instead of a live browser). |
| [BrowserGym](https://github.com/ServiceNow/BrowserGym) | Apache-2.0 | Borrowed the *observation / action abstraction, task spec, and evidence-based success evaluation* philosophy (real system state, not agent self-report). |
| [AgentLab](https://github.com/ServiceNow/AgentLab) | Apache-2.0 | Borrowed the *experiment-run / trajectory / benchmark / reproducibility* organization. |
| [Skyvern](https://github.com/Skyvern-AI/skyvern) | AGPL-3.0 | Borrowed product-thinking for the *Agent Monitor UI / workflow visualization*. We did **not** adopt AGPL code; the monitor is original. |

## License notes

- **BrowserGym / AgentLab** are Apache-2.0. We attribute them above. We did not
  include their source; if you vendor or adapt their code later, retain their
  `LICENSE` and copyright notices.
- **Skyvern** is AGPL-3.0. Its code was **not** used (only the product UX idea).
  If you later incorporate Skyvern source, you must comply with AGPL-3.0
  (including source-disclosure obligations).

## Runtime dependencies (backend)

The Python backend depends on the following PyPI packages (licenses noted):

- FastAPI — MIT
- Uvicorn — BSD
- SQLAlchemy — MIT
- Pydantic — MIT
- Pydantic-Settings — MIT
- HTTPX — BSD
- PyYAML — MIT
- Python-Multipart — MIT
- pytest / pytest-asyncio — MIT

## Frontend dependencies

- Vue 3 — MIT
- TypeScript — Apache-2.0
- Vite — MIT
- Element Plus — MIT
- Axios — MIT
- ECharts — Apache-2.0

All synthetic. No real hospital / MES data is included anywhere in this repo.
