<template>
  <div>
    <h2 class="h2m-page-title">生产执行 Production Execution</h2>
    <p class="h2m-page-sub">模拟 7 个生产阶段：称量 → 溶解 → 过滤 → 分装 → 贴签 → 包装 → 入库</p>

    <el-card class="h2m-card" shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="选择指令">
          <el-select v-model="selected" filterable placeholder="选择生产指令" @change="loadStages" style="width: 320px">
            <el-option v-for="o in orders" :key="o.id" :label="`${o.order_code} · ${o.product}`" :value="o.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <div v-if="stages.length">
        <el-steps :active="activeIndex" finish-status="success" align-center>
          <el-step v-for="s in stages" :key="s.stage_name" :title="label(s.stage_name)" :status="stepStatus(s)" />
        </el-steps>
        <el-divider />
        <el-table :data="stages" stripe>
          <el-table-column prop="stage_name" label="阶段" width="160">
            <template #default="{ row }">{{ label(row.stage_name) }}</template>
          </el-table-column>
          <el-table-column prop="stage_status" label="状态" width="140">
            <template #default="{ row }"><el-tag :type="statusType(row.stage_status)" size="small">{{ row.stage_status }}</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button size="small" type="success" :disabled="row.stage_status === 'COMPLETED'" @click="complete(row)">完成</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-else description="请选择一个生产指令查看执行阶段" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { ElMessage } from "element-plus";
import api, { ProductionOrder } from "@/api";

const orders = ref<ProductionOrder[]>([]);
const selected = ref<number | null>(null);
const stages = ref<any[]>([]);

const labels: Record<string, string> = {
  weighing: "称量", dissolution: "溶解", filtration: "过滤",
  filling: "分装", labeling: "贴签", packaging: "包装", storage: "入库",
};
const label = (s: string) => labels[s] || s;

const statusType = (s: string) =>
  s === "COMPLETED" ? "success" : s === "IN_PROGRESS" ? "warning" : s === "FAILED" ? "danger" : "info";

const activeIndex = computed(() => {
  let idx = 0;
  for (const s of stages.value) {
    if (s.stage_status === "COMPLETED") idx++;
    else break;
  }
  return idx;
});
const stepStatus = (s: any) =>
  s.stage_status === "COMPLETED" ? "success" : s.stage_status === "FAILED" ? "error" : "process";

async function loadOrders() {
  const { data } = await api.listOrders();
  orders.value = data;
  if (orders.value.length && selected.value === null) {
    selected.value = orders.value[0].id;
    loadStages();
  }
}
async function loadStages() {
  if (selected.value === null) return;
  const { data } = await api.getStages(selected.value);
  stages.value = data;
  if (!stages.value.length && selected.value) {
    await api.startOrder(selected.value);
    const r = await api.getStages(selected.value);
    stages.value = r.data;
  }
}
async function complete(row: any) {
  if (selected.value === null) return;
  await api.completeStage(selected.value, row.stage_name, "complete");
  ElMessage.success(`${label(row.stage_name)} 已完成`);
  loadStages();
}
onMounted(() => { loadOrders(); });
</script>
