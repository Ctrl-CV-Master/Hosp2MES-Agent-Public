<template>
  <el-container class="layout">
    <el-aside width="220px" class="sidebar">
      <div class="brand">
        <el-icon :size="22"><cpu /></el-icon>
        <span class="brand-title">Hosp2MES</span>
      </div>
      <el-menu :default-active="activeMenu" router background-color="#1f2d3d" text-color="#c0c4cc" active-text-color="#409eff">
        <el-menu-item index="/dashboard"><el-icon><data-board /></el-icon><span>仪表盘</span></el-menu-item>
        <el-menu-item index="/materials"><el-icon><box /></el-icon><span>物品主文件</span></el-menu-item>
        <el-menu-item index="/boms"><el-icon><connection /></el-icon><span>BOM 管理</span></el-menu-item>
        <el-menu-item index="/orders"><el-icon><document /></el-icon><span>生产指令</span></el-menu-item>
        <el-menu-item index="/execution"><el-icon><video-play /></el-icon><span>生产执行</span></el-menu-item>
        <el-menu-item index="/anomalies"><el-icon><warning /></el-icon><span>异常管理</span></el-menu-item>
        <el-menu-item index="/agent"><el-icon><monitor /></el-icon><span>Agent Monitor</span></el-menu-item>
        <el-menu-item index="/benchmark"><el-icon><trophy /></el-icon><span>Benchmark</span></el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <span class="topbar-title">{{ pageTitle }}</span>
        <span class="topbar-tag">Mock MES · Public Demo</span>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const activeMenu = computed(() => route.path);
const titles: Record<string, string> = {
  dashboard: "仪表盘 Dashboard",
  materials: "物品主文件 Materials",
  boms: "BOM 管理",
  orders: "生产指令 Production Orders",
  execution: "生产执行 Production Execution",
  anomalies: "异常管理 Anomalies",
  agent: "Agent Monitor",
  benchmark: "Benchmark Tasks",
};
const pageTitle = computed(() => titles[route.name as string] || "Hosp2MES");
</script>

<style scoped>
.layout { height: 100%; }
.sidebar { background: #1f2d3d; }
.brand { display: flex; align-items: center; gap: 8px; color: #fff; padding: 18px 16px; font-weight: 700; font-size: 18px; }
.brand-title { letter-spacing: 0.5px; }
.topbar { display: flex; align-items: center; justify-content: space-between; background: #fff; border-bottom: 1px solid #ebeef5; }
.topbar-title { font-weight: 600; font-size: 16px; }
.topbar-tag { font-size: 12px; color: #909399; background: #f4f4f5; padding: 4px 10px; border-radius: 12px; }
.main { background: var(--h2m-bg); padding: 20px; }
</style>
