# Agent 设计文档

## 1. 设计目标

Hosp2MES Agent 要解决的核心问题是：**如何让 LLM 在 MES 这类长周期、多步骤、状态易变的业务系统中可靠地完成端到端任务**,例如:创建物料 → 配置 BOM → 下达生产指令 → 完成七阶段生产 → 入库。

为此,Agent 强调四个能力:

1. **长周期规划(Long-Horizon Planning)**
2. **结构化进度记忆(Structured Progress Memory)**
3. **证据门控验证(Evidence-Gated Completion)**
4. **局部恢复(Local Recovery)**

## 2. 核心模块

### 2.1 Planner

- 输入:自然语言指令 + `expected_final_state`(目标状态字典)。
- 输出:`Plan` 对象,包含子目标列表。
- 实现:基于目标状态反推子目标,不依赖 LLM 生成动作细节,保证确定性。

```python
planner = Planner()
plan = planner.plan(
    instruction="为 DEMO-GLUCOSE-SOLUTION 创建 BOM 与生产指令",
    expected_final_state={"bom_exists": True, "production_order_status": "NOT_STARTED"}
)
print(plan.ids())  # ["create_bom", "create_production_order"]
```

### 2.2 Progress Memory

显式 JSON 结构,记录:

- `goal`: 总目标
- `subgoals`: 全部子目标
- `pending_subgoals`: 未完成
- `completed_subgoals`: 已完成
- `failed_subgoals`: 失败

避免把状态隐藏在对话历史中。

### 2.3 Verifier

Verifier 是 Agent 可信度的关键。它不询问 Agent “你做完了吗?”,而是**直接读取后端状态**:

```python
verifier.verify(observed_state, expected_state)
# 例如检查 material_exists=True 是否成立
```

### 2.4 Recovery Manager

当某一步验证失败时,Recovery Manager 决定局部动作:

- `retry`: 重试最近失败动作
- `reobserve`: 重新读取状态
- `compensate`: 执行补偿(如删除错误记录)
- `escalate`: 上报人类/停止

### 2.5 Trace Recorder

每一步生成 `TraceStep`:

```json
{
  "step": 1,
  "subgoal": "create_bom",
  "action": "create_bom",
  "result": "ok",
  "reasoning": "Create BOM BOM-DEMO-GLU-001 for DEMO-GLUCOSE-SOLUTION",
  "memory_state": { ... },
  "timestamp": "2026-08-20T12:00:00"
}
```

Trace 会发布到后端,Agent Monitor 实时渲染。

## 3. Skill 设计

| Skill | 功能 | 幂等策略 |
|-------|------|----------|
| `create_material` | 创建物料主文件 | 按 `material_code` 检查 |
| `create_bom` | 创建 BOM 与工艺路线 | 按 `bom_code` 检查 |
| `create_production_order` | 创建生产指令 | 按 `order_code` 检查 |
| `execute_production` | 驱动七阶段生产 | 按阶段状态补全缺失阶段 |

## 4. LLM 集成

支持两种 LLM Provider:

- `MockLLM`: 确定性规则,无需 API Key,用于评测与 CI。
- `DeepSeekLLM`: 兼容 DeepSeek API/OpenAI 格式,由 `LLM_PROVIDER=deepseek` 启用。

切换方式:

```bash
PYTHONPATH=.:backend python -m hosp2mes.run --task MES-DEMO-001 --provider mock
```

## 5. 与 GUI 的关系

当前公开演示使用 `ApiEnv`(REST 观测/执行),不依赖浏览器。`observation/browser_env.py` 已预留 `BrowserEnv` 扩展点,供后续接入 Playwright 真实 GUI 自动化。
