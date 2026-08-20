import { createRouter, createWebHistory } from "vue-router";
import MainLayout from "@/layout/MainLayout.vue";

const routes = [
  {
    path: "/",
    component: MainLayout,
    children: [
      { path: "", redirect: "/dashboard" },
      { path: "dashboard", name: "dashboard", component: () => import("@/views/Dashboard.vue") },
      { path: "materials", name: "materials", component: () => import("@/views/Materials.vue") },
      { path: "boms", name: "boms", component: () => import("@/views/Boms.vue") },
      { path: "orders", name: "orders", component: () => import("@/views/Orders.vue") },
      { path: "execution", name: "execution", component: () => import("@/views/Execution.vue") },
      { path: "anomalies", name: "anomalies", component: () => import("@/views/Anomalies.vue") },
      { path: "agent", name: "agent", component: () => import("@/views/AgentMonitor.vue") },
      { path: "benchmark", name: "benchmark", component: () => import("@/views/Benchmark.vue") },
    ],
  },
];

export default createRouter({
  history: createWebHistory(),
  routes,
});
