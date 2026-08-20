# 基准评测

## 1. 评测原则

- **可复现**: 每个任务在独立 SQLite 上运行,避免交叉污染。
- **真实验证**: Agent 声称成功后,Harness 重新读取后端状态并核对 `expected_final_state`。
- **公开透明**: 任务 YAML、评测脚本、结果全部开源。

## 2. 任务列表

| 任务 | 难度 | 目标 | 关键验证点 |
|------|------|------|------------|
| MES-DEMO-001 | 入门 | 创建新物料 | `material_exists = true` |
| MES-DEMO-002 | 标准 | 为目标产品创建 BOM 与生产指令 | `bom_exists = true`, `production_order_status = NOT_STARTED` |
| MES-DEMO-003 | Hero | 完整长周期:创建物料 → BOM → 指令 → 七阶段生产 → 入库,并注入 BOM 保存异常后恢复 | `material_exists`, `bom_exists`, `production_order_status = COMPLETED`, `storage_status = STORED`, `recovery_count >= 1` |

## 3. 运行方式

```bash
cd D:/Hosp2MES-Agent-Public
PYTHONPATH=.:backend python benchmark/e2e_probe.py
```

运行结束后会在 `benchmark/results/e2e_run.txt` 生成报告。

## 4. 评测指标

```python
EvaluationResult(
    task_id="MES-DEMO-001",
    success=True,
    subgoal_rate=1.0,
    step_count=4,
    recovery_count=0,
    premature_done=False,
    final_state_match=True,
)
```

- `success`: 所有验证门通过
- `subgoal_rate`: 已完成子目标 / 全部子目标
- `step_count`: Agent 执行步数
- `recovery_count`: 触发局部恢复次数
- `premature_done`: 是否未达目标就结束
- `final_state_match`: Harness 二次核对后端状态是否匹配

## 5. Hero 任务异常注入

MES-DEMO-003 在创建 BOM 前注入异常 `save_failure`,模拟 MES 保存接口临时故障:

```yaml
injected_anomalies:
  - target: bom
    type: save_failure
    message: "模拟 BOM 保存接口短暂失败"
```

Agent 的 `create_bom` Skill 第一次调用会失败,Recovery Manager 捕获后重试,第二次成功。该机制证明 Agent 具备**局部恢复**能力,而非简单重启整个任务。

## 6. 最新评测结果

运行 `benchmark/e2e_probe.py` 验证:

- MES-DEMO-001: success=True, recovery=0
- MES-DEMO-002: success=True, recovery=0
- MES-DEMO-003: success=True, recovery=1
