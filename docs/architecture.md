# Hosp2MES 系统架构

## 1. 整体定位

Hosp2MES-Agent-Public 是一个**面向制造执行系统(MES)的长周期 GUI Agent 公开演示项目**。它提供：

- 一个可独立运行的 Mock MES 后端(FastAPI + SQLite)。
- 一个基于 Vue 3 的可视化控制台。
- 一个可插拔的 Agent 框架 `hosp2mes/`，实现长周期规划、结构化进度记忆、证据门控验证与局部恢复。
- 一组公开基准任务(MES-DEMO-001/002/003)，用于可复现评测。

> 全部数据均为虚构演示数据，不含任何真实医院/工厂信息。

## 2. 架构分层

```
┌───────────────────────────────────────────────────────────────┐
│  frontend/          Vue 3 + Element Plus + ECharts            │
│  Dashboard / Materials / BOMs / Orders / Execution /          │
│  Anomalies / Agent Monitor / Benchmark                        │
└───────────────────────┬───────────────────────────────────────┘
                        │  REST /api/*
┌───────────────────────▼───────────────────────────────────────┐
│  backend/           FastAPI + SQLAlchemy + SQLite             │
│  Materials / BOMs / Orders / Execution / Anomalies /          │
│  Dashboard / AgentRun / Launch                                │
└───────────────────────┬───────────────────────────────────────┘
                        │  REST /api/*  (也被 Agent 直接调用)
┌───────────────────────▼───────────────────────────────────────┐
│  hosp2mes/          Agent 核心包                              │
│  planner / memory / observation / executor / verifier /       │
│  recovery / trace / evaluation / llm                          │
└───────────────────────────────────────────────────────────────┘
```

## 3. 数据模型

| 实体 | 说明 |
|------|------|
| `Material` | 物料主文件(原料/半成品/成品/包材) |
| `BOM` | 产品物料清单与工艺路线 |
| `BOMItem` | BOM 行项目(物料、用量) |
| `ProductionOrder` | 生产指令与状态(NOT_STARTED → RUNNING → COMPLETED/SCRAPPED) |
| `ExecutionStage` | 七阶段生产执行(称量 → 配液 → 灌装 → 灭菌 → 灯检 → 贴标 → 入库) |
| `Anomaly` | 生产异常(可注入/解决) |
| `AgentRun` | Agent 运行记录、Trace、验证结果 |

## 4. Agent 流水线

1. **Plan**: 根据自然语言指令与 `expected_final_state` 生成子目标序列。
2. **Execute**: 每个子目标调用 `Skill`(如创建物料、创建 BOM、创建订单、执行生产)。
3. **Verify**: 每个 Skill 执行后通过**证据门控**读取真实系统状态确认效果。
4. **Recover**: 当验证失败时,Recovery Manager 在本地尝试重试/补偿,不重新规划整段任务。
5. **Trace**: 每步记录为结构化 `TraceStep`,并发布到后端供 Agent Monitor 实时展示。

## 5. 关键技术决策

- **观测优先**: Agent 通过 `ApiEnv` 读取后端状态,而不是依赖执行动作的自我报告。
- **幂等性**: 所有创建类 Skill 按资源编码(BOM 编码、订单编码)检查存在性,避免重复创建。
- **隔离性**: 基准测试每个任务使用独立 SQLite 文件 + `configure_engine()`,保证可复现。
- **MockLLM 回退**: 无需 API Key 即可运行完整 E2E 评测,便于 CI 与公开演示。
