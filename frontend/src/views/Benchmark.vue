<template>
  <div>
    <h2 class="h2m-page-title">Benchmark Tasks</h2>
    <p class="h2m-page-sub">公开评测任务集（全部使用虚构演示数据）</p>

    <el-row :gutter="16">
      <el-col :span="8" v-for="t in tasks" :key="t.id">
        <el-card class="h2m-card" shadow="hover">
          <template #header>
            <span>{{ t.id }}</span>
            <el-tag size="small" type="primary" style="margin-left: 6px">{{ t.tag }}</el-tag>
          </template>
          <p style="min-height: 64px">{{ t.desc }}</p>
          <el-divider />
          <div class="exp">
            <div><b>期望最终状态</b></div>
            <div v-for="(v, k) in t.expected" :key="k" class="kv">{{ k }} = {{ String(v) }}</div>
          </div>
          <el-button type="primary" style="margin-top: 12px" @click="runInMonitor(t.id)">在 Monitor 中运行</el-button>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="h2m-card" shadow="never" style="margin-top: 8px">
      <template #header>命令行运行（无需前端）</template>
      <pre class="code-block"># 使用内置 MockLLM（无需 API Key）
PYTHONPATH=. python -m hosp2mes.run --task MES-DEMO-001
PYTHONPATH=. python -m hosp2mes.run --task MES-DEMO-002
PYTHONPATH=. python -m hosp2mes.run --task MES-DEMO-003

# 隔离环境批量评测
PYTHONPATH=.:backend python benchmark/e2e_probe.py</pre>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";
import api from "@/api";

const router = useRouter();
const tasks = [
  { id: "MES-DEMO-001", tag: "Task 01", desc: "创建一个新的 DEMO 产品物料，并确认物料主文件保存成功。", expected: { material_exists: true } },
  { id: "MES-DEMO-002", tag: "Task 02", desc: "查询目标产品，创建 BOM，配置物料，创建生产指令，并确认生产指令成功建立。", expected: { bom_exists: true, production_order_status: "NOT_STARTED" } },
  { id: "MES-DEMO-003", tag: "HERO", desc: "完整长任务：创建产品、BOM、指令，完成 7 阶段生产并入库，注入异常演示局部恢复。", expected: { material_exists: true, bom_exists: true, production_order_status: "COMPLETED", storage_status: "STORED" } },
];
async function runInMonitor(id: string) {
  await fetch("/api/agent/runs/launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: id, mode: "hosp2mes", provider: "mock" }),
  });
  router.push("/agent");
}
</script>

<style scoped>
.exp { background: #f5f7fa; padding: 10px 12px; border-radius: 6px; font-size: 13px; }
.kv { font-family: monospace; color: #606266; }
</style>
