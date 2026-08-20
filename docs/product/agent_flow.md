# Agent 内部流程

## 1. 启动阶段

```
用户/测试 → POST /api/agent/runs/launch
                ↓
          后端创建 AgentRun(status=RUNNING)
                ↓
          后台线程启动 hosp2mes.run
                ↓
          Agent.run() 接收 task_id
```

## 2. 规划阶段

```
读取 task YAML
      ↓
expected_final_state 解析为验证字典
      ↓
Planner.plan() 生成子目标序列
      ↓
ProgressMemory.from_plan() 初始化进度
```

例如 MES-DEMO-002:

```
goal: create BOM + production order
subgoals: [create_bom, create_production_order]
```

## 3. 执行阶段(按子目标循环)

```
for subgoal in pending_subgoals:
    skill = choose_skill(subgoal)
    action = skill.decide(env, memory)
    result = executor.execute(action)
    trace.record(step, action, result)
    publish(trace)  → 后端 AgentRun

    verification = verifier.verify(env.read_state(), expected_state)
    if verification.passed:
        memory.complete(subgoal)
    else:
        recovery = recovery_manager.decide(skill, verification)
        if recovery succeeded:
            memory.complete(subgoal)
        else:
            memory.fail(subgoal)
```

## 4. 验证阶段

每个 Skill 执行后必须满足对应 `expected_final_state` 子集:

- `create_material` → `material_exists=True`
- `create_bom` → `bom_exists=True`
- `create_production_order` → `production_order_status` 符合预期
- `execute_production` → `production_order_status=COMPLETED`, `storage_status=STORED`

## 5. 完成阶段

```
所有子目标完成
      ↓
最终验证全部通过
      ↓
AgentRun.status = DONE, success = True
      ↓
停止轮询,Agent Monitor 显示绿色 SUCCESS
```

## 6. Hero 任务异常流程(MES-DEMO-003)

```
创建 BOM 时
      ↓
ApiEnv 检测到 injected anomaly save_failure
      ↓
动作返回失败
      ↓
Verifier 未通过
      ↓
RecoveryManager 选择 retry
      ↓
重试成功,继续后续子目标
      ↓
最终 recovery_count = 1
```
