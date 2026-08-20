# 开发指南

## 1. 环境准备

### 后端(Python)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```

### 前端(Node.js)

```bash
cd frontend
npm install
```

## 2. 启动开发环境

### 2.1 后端

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Swagger UI: `http://127.0.0.1:8000/docs`

### 2.2 前端

```bash
cd frontend
npm run dev
```

访问: `http://127.0.0.1:5173`

前端通过 Vite 代理把 `/api` 转发到 `http://localhost:8000`。

## 3. 运行 Agent CLI

```bash
cd <repo-root>
PYTHONPATH=.:backend python -m hosp2mes.run --task MES-DEMO-001 --provider mock
```

可用任务: `MES-DEMO-001`, `MES-DEMO-002`, `MES-DEMO-003`。

## 4. 运行测试

```bash
cd <repo-root>
backend/.venv/Scripts/python.exe -m pytest tests/ -q
```

当前包含:

- `tests/backend/test_crud.py`: 后端 CRUD 与业务逻辑
- `tests/agent/test_core.py`: Planner / Memory / Verifier / Recovery / Evaluator 单元测试
- `tests/agent/test_e2e.py`: 完整 E2E,启动临时后端并驱动 Agent 完成三个 DEMO 任务

## 5. 运行基准

```bash
cd <repo-root>
PYTHONPATH=.:backend python benchmark/e2e_probe.py
```

结果写入 `benchmark/results/e2e_run.txt`。

## 6. 构建生产前端

```bash
cd frontend
npm run build
```

产物在 `frontend/dist/`。可使用 `npm run preview` 本地预览。

## 7. 项目结构

```
Hosp2MES-Agent-Public/
├── backend/              FastAPI 后端
├── frontend/             Vue 3 前端
├── hosp2mes/             Agent 核心包
├── benchmark/            基准任务与评测脚本
├── tests/                pytest 测试
├── docs/                 设计文档
├── assets/screenshots/   演示截图
├── .env.example          环境变量示例
├── README.md             项目总览
└── LICENSE               MIT
```

## 8. 注意事项

- 不要提交 `backend/mes_demo.db`、`.env`、API Key。
- 新增 Skill 时保持幂等:先读取状态,再决定执行/跳过。
- 新增任务时同步更新 `benchmark/tasks/`、测试与 `docs/benchmark.md`。
