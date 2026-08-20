# 产品需求文档(PRD)

## 1. 产品背景

制造业执行系统(MES)操作复杂、步骤长、业务规则多。传统 RPA 脚本脆弱,难以应对状态变化。Hosp2MES 希望展示一种**基于长周期 Agent 的 MES 操作范式**:Agent 像人类操作员一样,理解目标、分步执行、验证结果、局部恢复。

## 2. 目标用户

- **算法/Agent 研究者**:了解如何在 MES/ERP 场景中落地 GUI Agent。
- **招聘方/技术评审**:快速判断项目的工程完整度、可运行性、可扩展性。
- **企业 PoC 团队**:作为演示原型,验证 Agent + MES 集成的可行性。

## 3. 核心需求

### 3.1 Mock MES

- 物料主文件(CRUD)
- BOM 与工艺路线
- 生产指令与七阶段执行
- 异常注入/解决
- 仪表盘统计

### 3.2 Agent 框架

- 长周期规划
- 结构化进度记忆
- 证据门控验证
- 局部恢复
- 结构化 Trace

### 3.3 可视化控制台

- 仪表盘:生产完成率、最近指令
- 业务页面:Materials/BOMs/Orders/Execution/Anomalies
- Agent Monitor:实时/离线查看 Agent 运行与 Trace
- Benchmark:展示三个公开任务与一键运行入口

### 3.4 可复现评测

- 3 个公开任务,覆盖简单/标准/长周期+恢复场景
- Harness 独立后端运行,真实验证
- 输出结构化评分

## 4. 非功能需求

- **可公开**:无真实数据、无闭源依赖、无硬编码 API Key。
- **可运行**:一键启动后端 + 前端 + Agent。
- **可测试**:pytest + benchmark 均能通过。
- **可扩展**:模块化 Skill、可替换 LLM、可切换 REST/浏览器环境。

## 5. 交付边界

- V0.1: Mock MES + 可视化控制台
- V0.2: Agent 基线 + ApiEnv
- V0.3: Hosp2MES 核心(规划/记忆/验证/恢复)
- V0.4: Agent Monitor + Benchmark + Evaluation
- V1.0: 文档、README、测试、截图、GitHub 就绪
