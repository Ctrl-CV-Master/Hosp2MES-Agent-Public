# API 文档

后端启动后访问 Swagger UI:

```
http://127.0.0.1:8000/docs
```

## 1. 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 返回 `{ "status": "ok" }` |

## 2. 物料主文件

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/materials` | 列表/搜索 |
| POST | `/api/materials` | 创建物料 |
| GET | `/api/materials/{id}` | 详情 |
| DELETE | `/api/materials/{id}` | 删除 |

请求体示例:

```json
{
  "material_code": "MAT-DEMO-001",
  "material_name": "注射级氯化钾",
  "material_type": "raw",
  "unit": "kg",
  "specification": "≥99.5%"
}
```

## 3. BOM 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/boms` | BOM 列表 |
| POST | `/api/boms` | 创建 BOM |
| GET | `/api/boms/{id}` | BOM 详情 |
| POST | `/api/boms/{id}/materials` | 新增 BOM 物料 |
| DELETE | `/api/boms/{id}/materials/{item_id}` | 删除 BOM 物料 |

## 4. 生产指令

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/orders` | 列表 |
| POST | `/api/orders` | 创建生产指令 |
| GET | `/api/orders/{id}` | 详情 |
| POST | `/api/orders/{id}/execute` | 触发七阶段执行 |

## 5. 生产执行

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/execution/stages/{order_id}` | 查询某订单阶段 |
| POST | `/api/execution/stages/{order_id}` | 推进/操作阶段 |

## 6. 异常管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/anomalies` | 异常列表 |
| POST | `/api/anomalies` | 注入异常 |
| POST | `/api/anomalies/{id}/resolve` | 解决异常 |

## 7. 仪表盘

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard` | 今日任务、完成率、最近订单 |

## 8. Agent 运行

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agent/runs` | 运行记录列表 |
| GET | `/api/agent/runs/{id}` | 运行详情 |
| POST | `/api/agent/runs/launch` | 启动 Agent 任务 |

启动请求示例:

```json
{
  "task_id": "MES-DEMO-001",
  "mode": "hosp2mes",
  "provider": "mock",
  "backend_url": "http://127.0.0.1:8000"
}
```

响应 202,异步执行,通过 `/api/agent/runs/{id}` 轮询状态。
