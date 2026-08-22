<template>
  <div>
    <h2 class="h2m-page-title">物品主文件 Materials</h2>
    <p class="h2m-page-sub">创建 / 查询 / 修改 / 删除 物料主数据</p>

    <el-card class="h2m-card" shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="搜索">
          <el-input v-model="q" placeholder="物料编码 / 名称" aria-label="搜索物料" clearable @keyup.enter="load" />
        </el-form-item>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="openCreate">新建物料</el-button>
      </el-form>

      <el-table :data="rows" stripe v-loading="loading">
        <el-table-column prop="material_code" label="编码" width="140" />
        <el-table-column prop="material_name" label="名称" />
        <el-table-column prop="material_type" label="类型" width="110" />
        <el-table-column prop="unit" label="单位" width="80" />
        <el-table-column prop="specification" label="规格" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }"><el-tag size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" :title="editing ? '编辑物料' : '新建物料'" width="460px" aria-label="物料编辑对话框">
      <el-form :model="form" label-width="90px">
        <el-form-item label="物料编码"><el-input v-model="form.material_code" aria-label="物料编码" :disabled="editing" /></el-form-item>
        <el-form-item label="物料名称"><el-input v-model="form.material_name" aria-label="物料名称" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="form.material_type" aria-label="类型"><el-option v-for="t in types" :key="t" :label="t" :value="t" /></el-select></el-form-item>
        <el-form-item label="单位"><el-input v-model="form.unit" aria-label="单位" /></el-form-item>
        <el-form-item label="规格"><el-input v-model="form.specification" aria-label="规格" /></el-form-item>
        <el-form-item label="状态"><el-select v-model="form.status" aria-label="状态"><el-option label="ACTIVE" value="ACTIVE" /><el-option label="INACTIVE" value="INACTIVE" /></el-select></el-form-item>
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
import { ElMessage, ElMessageBox } from "element-plus";
import api, { Material } from "@/api";

const rows = ref<Material[]>([]);
const loading = ref(false);
const q = ref("");
const dialog = ref(false);
const editing = ref(false);
const types = ["raw", "solvent", "packaging", "intermediate"];
const form = reactive<Partial<Material>>({});

async function load() {
  loading.value = true;
  try {
    const { data } = await api.listMaterials(q.value || undefined);
    rows.value = data;
  } finally {
    loading.value = false;
  }
}
function openCreate() {
  editing.value = false;
  Object.assign(form, { material_code: "", material_name: "", material_type: "raw", unit: "kg", specification: "", status: "ACTIVE" });
  dialog.value = true;
}
function openEdit(row: Material) {
  editing.value = true;
  Object.assign(form, row);
  dialog.value = true;
}
async function save() {
  if (editing.value && form.id) {
    await api.updateMaterial(form.id, form);
    ElMessage.success("已更新");
  } else {
    await api.createMaterial(form);
    ElMessage.success("已创建");
  }
  dialog.value = false;
  load();
}
async function remove(row: Material) {
  await ElMessageBox.confirm(`删除物料 ${row.material_code}?`, "确认", { type: "warning" });
  await api.deleteMaterial(row.id!);
  ElMessage.success("已删除");
  load();
}
load();
</script>
