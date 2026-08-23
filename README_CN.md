# Hosp2MES-Agent（中文版）

> 面向制造执行系统（MES）的长周期 GUI Agent。

Hosp2MES-Agent 让 LLM Agent 能够通过真实浏览器 GUI 自主执行多页面
制造业务流程，具备结构化进度记忆、基于证据的完成校验、以及基于状态
差异的局部恢复。

![Hero demo](assets/demo/hosp2mes-agent-demo.gif)

[![CI](https://img.shields.io/badge/CI-passing-16a34a?logo=githubactions&logoColor=white)](../../actions)
![Tests](https://img.shields.io/badge/tests-54%20passing-2563eb)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.12-3776ab)
![License](https://img.shields.io/badge/license-MIT-0d9488)

## ✨ 核心特性

### 🏭 长周期 GUI 执行

`物料 → BOM → 生产指令 → 7 个生产阶段 → 入库` —— 通过真实 Chromium
（Playwright）驱动完整多页面 Vue 流程，而非 mock API。

### 🧠 真实 LLM 决策循环

`观察 → DeepSeek → 一个 GUI 动作 → 执行 → 再观察`。每一步携带
`policy_source`（deterministic / deepseek）、`llm_model`、
`llm_latency_ms`、`decision_rationale`。无预写动作序列。

### 🛡️ 基于证据的完成校验

`Agent DONE ≠ 任务成功`。仅当独立只读校验器（REST）确认实时业务状态
符合期望终态时，Agent 才算通过。

### 🔁 自适应恢复

`状态差异 → 失败诊断 → 依赖感知局部重规划 → GUI 修复 →
独立校验 → 恢复`。真实 BOM 丢弃故障可被检测并修复，**不重做**
已完成的物料子目标。

## 🤔 为什么是 Hosp2MES

### 传统 GUI Agent

```text
Task → Observe → Act → LLM says DONE
```

问题：
- 长任务进度丢失
- "提前 DONE" 无法检测
- 任意失败都要从头重跑
- 难以验证真实业务完成

### Hosp2MES

```text
Task → Plan(依赖感知子目标) → 结构化进度记忆
     → Observe–Decide–Act（每步一个动作）
     → 独立校验
     → 局部恢复（state diff → replan → resume）
```

## 🏗️ 架构

![Architecture](assets/architecture.png)

依赖感知规划驱动 **Hosp2MESAgent** 循环：结合 **Browser Observation**
（DOM + 可访问性 + 截图）、**DeepSeek Action Policy**（每步一个结构化
动作）和 **BrowserExecutor**（语义定位，无 XPath/固定坐标）。Agent 驱动
**Mock MES**（Vue 3 + FastAPI + SQLite）。每一步经过 **Independent Verifier**
（只读 REST）。失败进入 **Adaptive Recovery**（V1.3）而不重置。

> REST API 不参与 GUI 动作决策或业务状态修改，仅作为独立只读校验器，
> 用于子目标完成检查和最终业务状态验证。

## ✅ 真实验证

### 长周期 Hero（`MES-DEMO-003`）

| 指标 | 值 |
|---|---|
| policy | `llm-strict`（真实 DeepSeek） |
| GUI 步数 | 31 |
| LLM 调用 | 31（全部 `policy_source=deepseek`） |
| fallback | **0** |
| 子目标 | 4 / 4 |
| 最终状态 | `material_exists=true`、`bom_exists=true`、`production_order_status=COMPLETED`、`storage_status=STORED` |

### 自适应恢复 Hero（`MES-DEMO-RECOVERY-001`）

| 指标 | 值 |
|---|---|
| 故障 | `FAULT-BOM-001`（BOM 创建后被丢弃，`discard_state_change` once，由测试 harness 注入——Agent 不知情） |
| policy | `llm-strict`（真实 DeepSeek） |
| 诊断 | `MISSING_PREREQUISITE`（`bom.exists` 期望 true / 实际 false） |
| 局部重规划 | `preserve create_material` · `reactivate create_bom` · `invalidate downstream` · `resume_from create_bom` |
| 修复步数 | 7（仅修复 episode） |
| `subgoal_execution_counts` | `{create_material:1, create_bom:2, create_production_order:1, execute_production:1}` |
| 已完成子目标被重做 | **0**（物料从未重跑） |
| 最终状态 | 全部校验通过 |

### 测试

**54 tests，全部通过** —— 单元、GUI E2E、LLM policy 模式、自适应恢复
（state diff / 诊断 / 依赖感知重规划 / 真实执行计数器 / 修复 episode
边界）、premature-DONE 指标。

## 🚀 快速开始

需要 **Python 3.10+**、**Node 20+** 和 `playwright install chromium`。
确定性 smoke 不需要 LLM Key；DeepSeek 运行需本地 `.env` 中的
`LLM_API_KEY`（git-ignored）。

```bash
git clone https://github.com/Ctrl-CV-Master/Hosp2MES-Agent-Public.git
cd Hosp2MES-Agent-Public
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
.venv/Scripts/python.exe -m pip install playwright pytest
.venv/Scripts/python.exe -m playwright install chromium
cd frontend && npm ci && npm run build && cd ..

.venv/Scripts/python.exe -m pytest tests/ -q
PYTHONPATH=.:backend .venv/Scripts/python.exe benchmark/e2e_probe.py

# (可选) 真实 DeepSeek Hero——需要 .env 中的 LLM_API_KEY
.venv/Scripts/python.exe run_llm_recovery.py --policy llm-strict
```

## 🤖 三种 Agent

| Agent | 文件 | 决策 |
|---|---|---|
| **SemanticSkillAgent**（Skill 基线） | `hosp2mes/agents/skill_agent.py` | 每个 subgoal 一段**预写**语义动作序列（确定性 baseline） |
| **Hosp2MESAgent**（LLM action policy） | `hosp2mes/agents/hosp2mes_agent.py` | **每步一个动作**：`GOAL+SUBGOAL+MEMORY+OBSERVATION → policy → 1 action`。三种 `--policy`：`deterministic` / `llm` / `llm-strict` |
| **AgentS3Adapter**（外部） | `hosp2mes/agents/agent_s3_adapter.py` | 桥接官方 [Agent S3](https://github.com/simular-ai/Agent-S)（Apache-2.0，`gui-agents`）。**Adapter ready — runtime not yet evaluated**（需 LLM Key + UI-TARS grounding 端点） |

`Hosp2MESAgent` 策略输出严格结构化、公开安全：

```json
{ "action": "click", "target": {"within": {"role": "row", "text": "称量"},
                              "role": "button", "name": "完成"},
  "value": null, "rationale": "短的公开理由" }
```

不产生、不保存私有 chain-of-thought。

## 📊 基准

| 任务 | 模式 | 结果 | 说明 |
|---|---|---|---|
| `MES-DEMO-001` | api | ✅ | 创建物料 |
| `MES-DEMO-002` | api | ✅ | BOM + 生产指令 |
| `MES-DEMO-003`（Hero） | api | ✅ | 全流程 + 局部恢复（recovery=1） |
| `MES-DEMO-GUI-001` | browser | ✅ | 通过 Playwright 创建物料 |
| `MES-DEMO-003`（Hero） | browser | ✅ | GUI 完成 物料→BOM→指令→7 阶段→入库 |
| `MES-DEMO-RECOVERY-001` | browser | ✅ | 故障注入 + 自适应恢复（DeepSeek `llm-strict`） |

## 📂 公开证据

完整本地 artifacts 不入 Git（每次跑会产生数十张截图）。精选、脱敏的
公开证据已发布：

- 长周期 Hero：[`examples/evidence/long_horizon_hero/`](examples/evidence/long_horizon_hero/)
- 自适应恢复 Hero：[`examples/evidence/recovery_hero/`](examples/evidence/recovery_hero/)

> 完整 artifacts 在本地 `artifacts/runs/` 生成且不入 Git。可用
> `python scripts/export_evidence.py hero|recovery <run_id>` 重新导出。

## ⚠️ 已知限制

- **Mock MES**——合成数据。无真实医院/工厂连接。不要宣称"production-ready industrial agent"。
- **单环境**——Mock MES 跑在单个 FastAPI + SQLite 进程。
- **真实 DeepSeek 运行需自备 key**——仓库不提交 `.env`。
- **Agent S3 adapter**——`gui-agents` 已安装，adapter 已构造；真实 `predict()` 需 worker LLM key **与** UI-TARS grounding 端点（未评测）。
- **恢复 demo**是单故障注入场景下的状态差异局部重规划，不是通用自愈 agent。

## 📄 License

MIT — 见 [LICENSE](LICENSE)。

---

> 英文版：[README.md](README.md)
