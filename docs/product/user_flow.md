# 用户流程

## 1. 首次体验

1. 克隆仓库
2. 启动后端 `uvicorn app.main:app --port 8000`
3. 启动前端 `npm run dev`
4. 打开浏览器 `http://127.0.0.1:5173`
5. 默认进入仪表盘,看到今日任务与完成率

## 2. 浏览业务数据

用户可依次点击左侧菜单:

- **物品主文件**:查看/搜索物料
- **BOM 管理**:查看 BOM 与物料清单
- **生产指令**:查看订单状态
- **生产执行**:查看/推进七阶段生产
- **异常管理**:查看/注入/解决异常

## 3. 启动 Agent 任务

1. 进入 **Agent Monitor**
2. 在“启动运行”面板选择任务(MES-DEMO-001/002/003)
3. 选择模式(Hosp2MES/Baseline)
4. 点击“运行任务”
5. 页面自动轮询运行状态,下方运行记录自动高亮最新任务
6. 右侧面板显示:目标、子目标完成进度、最终验证、Agent Trace

## 4. 查看 Benchmark

1. 进入 **Benchmark** 页面
2. 查看三个公开任务卡片与期望最终状态
3. 点击“在 Monitor 中运行”跳转 Agent Monitor 并预填任务
4. 或在命令行执行 `python -m hosp2mes.run --task MES-DEMO-XXX`

## 5. 验证结果

- Agent Trace 中每一步包含动作、结果、推理摘要
- 最终验证显示“all expected conditions observed in live system state”
- 用户可切换到对应业务页面(BOM/Orders)人工核对数据
