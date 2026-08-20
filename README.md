# Hosp2MES-Agent-Public

> 一个面向制造执行系统(MES)的长周期 GUI Agent 公开演示项目。

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Vue 3](https://img.shields.io/badge/frontend-Vue%203%20%2B%20TypeScript-success)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-green)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Hosp2MES** 演示了如何让 Agent 在 MES 业务系统中完成端到端长周期任务:创建物料主文件 → 配置 BOM 与工艺路线 → 下达生产指令 → 完成七阶段生产 → 入库。项目包含一个可独立运行的 Mock MES 后端、一个 Vue 3 可视化控制台、一个模块化 Agent 框架,以及 3 个公开基准任务。

全部数据均为虚构演示数据,不含任何真实医院或工厂信息。

![Dashboard](assets/screenshots/dashboard.png)

---

## ✨ 核心特性

- **长周期规划(Long-Horizon Planning)**:将高层目标自动分解为可执行子目标。
- **结构化进度记忆(Structured Progress Memory)**:显式记录已完成/待执行/失败子目标,不依赖对话历史。
- **证据门控验证(Evidence-Gated Verification)**:每步执行后读取真实后端状态验证,不盲信 Agent 自评。
- **局部恢复(Local Recovery)**:遇到注入异常时重试/补偿,而不是重启整段任务。
- **Agent Trace 与 Monitor**:每步动作、结果、推理摘要实时发布到前端。
- **MockLLM 回退**:无需 API Key 即可运行完整 E2E 评测。
- **公开基准**:MES-DEMO-001/002/003,覆盖简单创建、标准流程、长周期+恢复场景。

---

## 🚀 快速开始

### 1. 克隆并进入项目

```bash
cd D:\Hosp2MES-Agent-Public
```

### 2. 启动后端

```bash
cd backend
.venv/Scripts/activate
uvicorn app.main:app --reload --port 8000
```

后端 Swagger UI: `http://127.0.0.1:8000/docs`

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开浏览器: `http://127.0.0.1:5173`

### 4. 运行 Agent(命令行)

```bash
cd <repo-root>
PYTHONPATH=.:backend python -m hosp2mes.run --task MES-DEMO-001 --provider mock
```

可用任务: `MES-DEMO-001`、`MES-DEMO-002`、`MES-DEMO-003`。

---

## 📊 运行基准评测

```bash
cd <repo-root>
PYTHONPATH=.:backend python benchmark/e2e_probe.py
```

最新验证结果:

| 任务 | success | recovery_count |
|------|---------|----------------|
| MES-DEMO-001 | ✅ | 0 |
| MES-DEMO-002 | ✅ | 0 |
| MES-DEMO-003(Hero) | ✅ | 1 |

---

## 🧪 运行测试

```bash
cd <repo-root>
backend/.venv/Scripts/python.exe -m pytest tests/ -q
```

当前共 20 个测试全部通过:

- 后端 CRUD 与业务逻辑
- Agent Planner / Memory / Verifier / Recovery / Evaluator 单元测试
- 完整 E2E(临时后端 + Agent 完成三个 DEMO 任务)

---

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + ECharts + Axios |
| 后端 | Python + FastAPI + SQLAlchemy + SQLite + Pydantic |
| Agent | 模块化 Skill + MockLLM/DeepSeek + ApiEnv(REST) + BrowserEnv 扩展点 |
| 评测 | pytest + 自定义 E2E Harness |

---

## 📁 项目结构

```
Hosp2MES-Agent-Public/
├── backend/              # FastAPI + SQLite Mock MES
│   ├── app/
│   │   ├── routers/      # REST API
│   │   ├── services/     # 业务逻辑
│   │   ├── models.py     # SQLAlchemy 模型
│   │   ├── schemas.py    # Pydantic 模型
│   │   ├── seed.py       # 演示数据
│   │   └── main.py       # FastAPI 入口
│   └── requirements.txt
├── frontend/             # Vue 3 控制台
│   ├── src/
│   │   ├── views/        # Dashboard / Materials / BOMs / Orders /
│   │   │                 # Execution / Anomalies / AgentMonitor / Benchmark
│   │   ├── api/          # Axios 封装
│   │   └── router/       # Vue Router
│   └── package.json
├── hosp2mes/             # Agent 框架
│   ├── agent/
│   ├── planner/
│   ├── memory/
│   ├── observation/
│   ├── executor/
│   ├── verifier/
│   ├── recovery/
│   ├── trace/
│   ├── evaluation/
│   └── llm.py
├── benchmark/            # 基准任务与评测脚本
├── tests/                # pytest 测试
├── docs/                 # 设计文档
├── assets/screenshots/   # 演示截图
└── README.md
```

---

## 📸 界面截图

| 仪表盘 | BOM 管理 | Agent Monitor | Benchmark |
|--------|----------|---------------|-----------|
| ![](assets/screenshots/dashboard.png) | ![](assets/screenshots/boms.png) | ![](assets/screenshots/agent.png) | ![](assets/screenshots/benchmark.png) |

更多截图见 [`assets/screenshots/`](assets/screenshots/)。

---

## 📚 文档

- [架构设计](docs/architecture.md)
- [Agent 设计](docs/agent_design.md)
- [API 文档](docs/api.md)
- [基准评测](docs/benchmark.md)
- [开发指南](docs/development.md)
- [PRD](docs/product/PRD.md)
- [用户流程](docs/product/user_flow.md)
- [Agent 流程](docs/product/agent_flow.md)
- [开发状态](DEVELOPMENT_STATUS.md)

---

## 🔧 环境变量

复制 `.env.example` 为 `.env`,按需填写:

```bash
cp .env.example .env
```

主要变量:

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | SQLite 路径 | `sqlite:///./mes_demo.db` |
| `AGENT_LLM_PROVIDER` | LLM 提供者(`mock` / `deepseek`) | `mock` |
| `LLM_API_KEY` | DeepSeek 兼容 API Key | 空 |
| `LLM_BASE_URL` | DeepSeek 兼容端点 | 空 |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
| `BACKEND_BASE_URL` | Agent 访问后端的地址 | `http://127.0.0.1:8000` |

> 公开演示默认使用 `mock` provider,无需填写 API Key。

---

## ⚠️ 已知限制

- `BrowserEnv`(Playwright GUI 自动化)当前为预留扩展点;公开演示通过 `ApiEnv`(REST)运行,无需浏览器。
- 生产环境应使用 PostgreSQL 等服务器级数据库替换 SQLite。

---

## 📄 许可证

[MIT](LICENSE)

第三方依赖声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

---

## 🤝 贡献

欢迎 Issue 与 PR。新增 Skill 或任务时,请同步更新 `tests/`、`benchmark/` 与 `docs/`。
