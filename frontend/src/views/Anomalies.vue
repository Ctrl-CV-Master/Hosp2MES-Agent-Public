<template>
  <div>
    <h2 class="h2m-page-title">异常管理 Anomalies</h2>
    <p class="h2m-page-sub">人工注入故障，用于演示 Agent 的失败检测与局部恢复（Local Recovery）</p>

    <el-card class="h2m-card" shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width: 160px">
            <el-option label="保存失败 save_failure" value="save_failure" />
            <el-option label="数据缺失 missing_data" value="missing_data" />
            <el-option label="状态异常 status_error" value="status_error" />
            <el-option label="校验错误 validation_error" value="validation_error" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标">
          <el-select v-model="form.target" style="width: 140px">
            <el-option label="物料 material" value="material" />
            <el-option label="BOM bom" value="bom" />
            <el-option label="指令 order" value="order" />
            <el-option label="全局 global" value="global" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="form.message" placeholder="故障描述" /></el-form-item>
        <el-button type="danger" @click="inject">注入异常</el-button>
      </el-form>

      <el-alert type="info" :closable="false" style="margin-bottom: 12px"
        title="提示：在 Agent Monitor 中运行 MES-DEMO-003 前先注入一个 BOM 保存失败，可观察 Agent 检测故障→清除故障→重试的局部恢复过程。" />

      <el-table :data="rows" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="type" label="类型" width="160" />
        <el-table-column prop="target" label="目标" width="110" />
        <el-table-column prop="message" label="说明" />
        <el-table-column prop="active" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.active ? 'danger' : 'info'" size="small">{{ row.active ? "生效中" : "已解除" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button size="small" type="success" :disabled="!row.active" @click="resolve(row)">解除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import api, { Anomaly } from "@/api";

const rows = ref<Anomaly[]>([]);
const form = reactive<Partial<Anomaly>>({ type: "save_failure", target: "bom", message: "manual demo fault" });

async function load() {
  const { data } = await api.listAnomalies();
  rows.value = data;
}
async function inject() {
  await api.createAnomaly(form);
  ElMessage.success("已注入异常");
  load();
}
async function resolve(row: Anomaly) {
  await api.resolveAnomaly(row.id);
  ElMessage.success("已解除");
  load();
}
onMounted(load);
</script>
