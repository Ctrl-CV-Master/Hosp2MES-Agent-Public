<template>
  <div>
    <h2 class="h2m-page-title">仪表盘 Dashboard</h2>
    <p class="h2m-page-sub">Mock MES 今日生产概览（全部为虚构演示数据）</p>

    <el-row :gutter="16">
      <el-col :span="4" v-for="s in stats" :key="s.label">
        <el-card class="h2m-card stat" shadow="hover">
          <div class="stat-label">{{ s.label }}</div>
          <div class="stat-value">{{ s.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="10">
        <el-card class="h2m-card" shadow="never">
          <template #header>生产完成率</template>
          <div ref="pieRef" style="height: 280px"></div>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card class="h2m-card" shadow="never">
          <template #header>最近生产指令</template>
          <el-table :data="recent" size="small" stripe>
            <el-table-column prop="order_code" label="指令号" />
            <el-table-column prop="product" label="产品" />
            <el-table-column prop="batch" label="批次" />
            <el-table-column prop="status" label="状态">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue";
import * as echarts from "echarts";
import api, { DashboardSummary } from "@/api";

const stats = ref<any[]>([]);
const recent = ref<any[]>([]);
const pieRef = ref<HTMLElement>();
let chart: echarts.ECharts | null = null;

const statusType = (s: string) =>
  s === "COMPLETED" ? "success" : s === "IN_PROGRESS" ? "warning" : s === "FAILED" ? "danger" : "info";

async function load() {
  const { data } = await api.dashboard();
  const d = data as DashboardSummary;
  stats.value = [
    { label: "今日任务", value: d.today_tasks },
    { label: "已完成", value: d.completed },
    { label: "进行中", value: d.in_progress },
    { label: "异常", value: d.anomalies },
    { label: "完成率", value: (d.completion_rate * 100).toFixed(0) + "%" },
  ];
  recent.value = d.recent_orders || [];
  await nextTick();
  renderPie(d.completed, d.in_progress, d.anomalies);
}

function renderPie(completed: number, inProgress: number, anomalies: number) {
  if (!pieRef.value) return;
  chart = echarts.init(pieRef.value);
  chart.setOption({
    tooltip: { trigger: "item" },
    legend: { bottom: 0 },
    series: [
      {
        type: "pie",
        radius: ["45%", "70%"],
        label: { show: false },
        data: [
          { name: "已完成", value: completed, itemStyle: { color: "#67c23a" } },
          { name: "进行中", value: inProgress, itemStyle: { color: "#e6a23c" } },
          { name: "异常", value: anomalies, itemStyle: { color: "#f56c6c" } },
        ],
      },
    ],
  });
}

onMounted(load);
</script>

<style scoped>
.stat-label { color: #909399; font-size: 13px; }
.stat-value { font-size: 26px; font-weight: 700; margin-top: 6px; }
</style>
