<template>
  <div>
    <h2 class="h2m-page-title">BOM 管理</h2>
    <p class="h2m-page-sub">为产品配置物料清单（BOM）与工艺路线</p>

    <el-card class="h2m-card" shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="产品">
          <el-input v-model="product" placeholder="按产品筛选" clearable @keyup.enter="load" />
        </el-form-item>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button type="success" @click="openCreate">新建 BOM</el-button>
      </el-form>

      <el-table :data="rows" stripe v-loading="loading">
        <el-table-column prop="bom_code" label="BOM 编码" width="150" />
        <el-table-column prop="product" label="产品" width="200" />
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }"><el-tag size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="物料数" width="90">
          <template #default="{ row }">{{ row.materials?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button size="small" @click="openItems(row)">物料明细</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" title="新建 BOM" width="460px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="BOM 编码"><el-input v-model="form.bom_code" /></el-form-item>
        <el-form-item label="产品"><el-input v-model="form.product" /></el-form-item>
        <el-form-item label="版本"><el-input v-model="form.version" /></el-form-item>
        <el-form-item label="工艺路线">
          <el-input v-model="form.route" placeholder="weighing>dissolution>...>storage" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="itemsDialog" title="BOM 物料明细" width="560px">
      <div v-if="current">
        <el-tag>{{ current.bom_code }} · {{ current.product }}</el-tag>
        <el-divider />
        <el-table :data="current.materials || []" size="small">
          <el-table-column prop="material_code" label="物料编码" />
          <el-table-column prop="quantity" label="数量" width="100" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="removeItem(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-divider />
        <el-form :inline="true" @submit.prevent>
          <el-form-item label="物料编码"><el-input v-model="newItem.material_code" /></el-form-item>
          <el-form-item label="数量"><el-input-number v-model="newItem.quantity" :min="0" /></el-form-item>
          <el-button type="primary" @click="addItem">添加</el-button>
        </el-form>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import api, { BOM } from "@/api";

const rows = ref<BOM[]>([]);
const loading = ref(false);
const product = ref("");
const dialog = ref(false);
const itemsDialog = ref(false);
const current = ref<BOM | null>(null);
const form = reactive<Partial<BOM>>({});
const newItem = reactive<{ material_code: string; quantity: number }>({ material_code: "", quantity: 1 });

async function load() {
  loading.value = true;
  try {
    const { data } = await api.listBoms(product.value || undefined);
    rows.value = data;
  } finally {
    loading.value = false;
  }
}
function openCreate() {
  Object.assign(form, { bom_code: "", product: "", version: "1.0", route: "weighing>dissolution>filtration>filling>labeling>packaging>storage" });
  dialog.value = true;
}
async function save() {
  await api.createBom(form);
  ElMessage.success("BOM 已创建");
  dialog.value = false;
  load();
}
function openItems(row: BOM) {
  current.value = row;
  itemsDialog.value = true;
}
async function addItem() {
  if (!current.value) return;
  await api.addBomItem(current.value.id, { ...newItem });
  ElMessage.success("已添加");
  await refreshItems();
}
async function removeItem(row: any) {
  if (!current.value) return;
  await api.removeBomItem(current.value.id, row.id);
  ElMessage.success("已删除");
  await refreshItems();
}
async function refreshItems() {
  if (!current.value) return;
  const { data } = await api.listBoms();
  current.value = data.find((b) => b.id === current.value!.id) || null;
  // backend returns BOM.materials (not items)
}
load();
</script>
