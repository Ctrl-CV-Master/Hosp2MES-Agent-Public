<template>
  <div>
    <h2 class="h2m-page-title">生产指令 Production Orders</h2>
    <p class="h2m-page-sub">创建生产指令并启动生产</p>

    <el-card class="h2m-card" shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="产品">
          <el-input v-model="product" placeholder="按产品筛选" clearable @keyup.enter="load" />
        </el-form-item>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button type="success" @click="openCreate">新建指令</el-button>
      </el-form>

      <el-table :data="rows" stripe v-loading="loading">
        <el-table-column prop="order_code" label="指令号" width="160" />
        <el-table-column prop="product" label="产品" width="200" />
        <el-table-column prop="batch" label="批次" width="130" />
        <el-table-column prop="quantity" label="数量" width="80" />
        <el-table-column prop="status" label="状态" width="130">
          <template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" type="warning" :disabled="row.status !== 'NOT_STARTED'" @click="start(row)">启动</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" title="新建生产指令" width="460px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="指令号"><el-input v-model="form.order_code" /></el-form-item>
        <el-form-item label="产品"><el-input v-model="form.product" /></el-form-item>
        <el-form-item label="批次"><el-input v-model="form.batch" /></el-form-item>
        <el-form-item label="数量"><el-input-number v-model="form.quantity" :min="1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import api, { ProductionOrder } from "@/api";

const rows = ref<ProductionOrder[]>([]);
const loading = ref(false);
const product = ref("");
const dialog = ref(false);
const form = reactive<Partial<ProductionOrder>>({});

const statusType = (s: string) =>
  s === "COMPLETED" ? "success" : s === "IN_PROGRESS" ? "warning" : s === "FAILED" ? "danger" : "info";

async function load() {
  loading.value = true;
  try {
    const { data } = await api.listOrders(product.value || undefined);
    rows.value = data;
  } finally {
    loading.value = false;
  }
}
function openCreate() {
  Object.assign(form, { order_code: "", product: "", batch: "", quantity: 1 });
  dialog.value = true;
}
async function save() {
  await api.createOrder(form);
  ElMessage.success("生产指令已创建");
  dialog.value = false;
  load();
}
async function start(row: ProductionOrder) {
  await api.startOrder(row.id);
  ElMessage.success("已启动生产");
  load();
}
load();
</script>
