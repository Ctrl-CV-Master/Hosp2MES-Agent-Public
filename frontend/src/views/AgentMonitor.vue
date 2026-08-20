<template>
  <div>
    <h2 class="h2m-page-title">Agent Monitor</h2>
    <p class="h2m-page-sub">实时观察 Hosp2MES Agent 的任务规划、执行、证据验证与局部恢复</p>

    <el-row :gutter="16">
      <!-- Left: control + run list -->
      <el-col :span="8">
        <el-card class="h2m-card" shadow="never">
          <template #header>启动运行</template>
          <el-form label-width="70px">
            <el-form-item label="任务">
              <el-select v-model="launch.task_id" style="width: 100%">
                <el-option label="MES-DEMO-001 · 物料创建" value="MES-DEMO-001" />
                <el-option label="MES-DEMO-002 · BOM+指令" value="MES-DEMO-002" />
                <el-option label="MES-DEMO-003 · Hero 长任务" value="MES-DEMO-003" />
              </el-select>
            </el-form-item>
            <el-form-item label="模式">
              <el-radio-group v-model="launch.mode">
                <el-radio value="hosp2mes">Hosp2MES</el-radio>
                <el-radio value="baseline">Baseline</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="launching" @click="runTask">运行任务</el-button>
              <el-button @click="loadRuns">刷新</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="h2m-card" shadow="never" style="margin-top: 16px">
          <template #header>运行记录</template>
          <el-table :data="runs" highlight-current-row @current-change="onSelect" size="small">
            <el-table-column prop="id" label="#" width="50" />
            <el-table-column prop="task_id" label="任务" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.status === 'DONE' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- Right: live view -->
      <el-col :span="16">
        <el-card class="h2m-card" shadow="never" v-if="current">
          <template #header>
            <span>运行 #{{ current.id }} · {{ current.task_id }}</span>
            <el-tag :type="current.status === 'DONE' ? 'success' : 'warning'" size="small" style="margin-left: 8px">
              {{ current.status }}
            </el-tag>
            <span v-if="current.success !== null" style="margin-left: 8px">
              <el-tag :type="current.success ? 'success' : 'danger'" size="small">
                {{ current.success ? "SUCCESS" : "FAIL" }}
              </el-tag>
            </span>
          </template>

          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="Goal">{{ current.goal || current.task_id }}</el-descriptions-item>
            <el-descriptions-item label="当前子目标">
              <span class="h2m-status-running">{{ liveSubgoal || "-" }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="步数">Step {{ current.step_count }}</el-descriptions-item>
            <el-descriptions-item label="恢复次数">
              <strong :style="{ color: current.recovery_count ? '#e6a23c' : '#67c23a' }">{{ current.recovery_count }}</strong>
            </el-descriptions-item>
            <el-descriptions-item label="已完成子目标" :span="2">
              <el-tag v-for="s in completedSubgoals" :key="s" type="success" size="small" style="margin: 2px">{{ s }}</el-tag>
              <span v-if="!completedSubgoals.length" class="h2m-page-sub">—</span>
            </el-descriptions-item>
            <el-descriptions-item label="待执行子目标" :span="2">
              <el-tag v-for="s in pendingSubgoals" :key="s" type="info" size="small" style="margin: 2px">{{ s }}</el-tag>
              <span v-if="!pendingSubgoals.length" class="h2m-page-sub">—</span>
            </el-descriptions-item>
            <el-descriptions-item label="失败子目标" :span="2">
              <el-tag v-for="s in failedSubgoals" :key="s" type="danger" size="small" style="margin: 2px">{{ s }}</el-tag>
              <span v-if="!failedSubgoals.length" class="h2m-page-sub">—</span>
            </el-descriptions-item>
            <el-descriptions-item label="最近动作" :span="2">{{ current.last_action || "-" }}</el-descriptions-item>
            <el-descriptions-item label="最终验证" :span="2">{{ current.final_verification || "进行中…" }}</el-descriptions-item>
          </el-descriptions>

          <el-divider>Agent Trace（每步证据）</el-divider>
          <el-table :data="traceSteps" height="320" size="small" stripe>
            <el-table-column prop="step" label="#" width="50" />
            <el-table-column prop="subgoal" label="子目标" width="150" />
            <el-table-column prop="action" label="动作" width="170" />
            <el-table-column prop="result" label="结果" width="120">
              <template #default="{ row }">
                <span :class="row.result.startsWith('FAIL') ? 'h2m-status-fail' : 'h2m-status-done'">{{ row.result }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="reasoning_summary" label="推理摘要" show-overflow-tooltip />
          </el-table>
        </el-card>

        <el-empty v-else description="选择一个运行记录，或点击左侧运行任务" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed } from "vue";
import { ElMessage } from "element-plus";
import api, { AgentRun } from "@/api";

const runs = ref<AgentRun[]>([]);
const current = ref<AgentRun | null>(null);
const launching = ref(false);
const selectedId = ref<number | null>(null);
const launch = reactive({ task_id: "MES-DEMO-003", mode: "hosp2mes" });
let timer: any = null;

const traceSteps = computed(() => (current.value?.trace as any[]) || []);

// Progress Memory is embedded in every trace step's memory_state; surface the
// latest snapshot so the Monitor shows real structured progress (not chat text).
const lastMemory = computed(() => {
  const t = traceSteps.value;
  if (!t.length) return null;
  return t[t.length - 1]?.memory_state || null;
});
const completedSubgoals = computed(() => lastMemory.value?.completed_subgoals || []);
const pendingSubgoals = computed(() => lastMemory.value?.pending_subgoals || []);
const failedSubgoals = computed(() => lastMemory.value?.failed_subgoals || []);
const liveSubgoal = computed(
  () => current.value?.current_subgoal || lastMemory.value?.current_subgoal || "-"
);

async function loadRuns() {
  const { data } = await api.listAgentRuns();
  runs.value = data;
  // Auto-select the latest run so the monitor shows trace details on first load.
  if (data.length && selectedId.value === null) {
    await selectRun(data[0].id);
  }
}
async function runTask() {
  launching.value = true;
  try {
    // The launch endpoint spins up the agent (mock LLM) and streams its trace
    // to a freshly created AgentRun record on this backend.
    await fetch("/api/agent/runs/launch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_id: launch.task_id,
        mode: launch.mode,
        provider: "mock",
        backend_url: window.location.origin,
      }),
    });
    ElMessage.success("已启动，正在实时追踪…");
    await loadRuns();
    if (runs.value.length) {
      const newest = runs.value[0]; // ordered by id desc
      await selectRun(newest.id);
    }
  } finally {
    launching.value = false;
  }
}
function onSelect(row: AgentRun | null) {
  if (row) selectRun(row.id);
}
async function selectRun(id: number) {
  selectedId.value = id;
  const { data } = await api.getAgentRun(id);
  current.value = data;
}
function tick() {
  if (selectedId.value !== null) {
    api.getAgentRun(selectedId.value).then(({ data }) => {
      current.value = data;
      if (data.status === "DONE") stopPoll();
    }).catch(() => {});
  }
}
function startPoll() {
  stopPoll();
  timer = setInterval(tick, 1500);
}
function stopPoll() {
  if (timer) { clearInterval(timer); timer = null; }
}
onMounted(async () => { await loadRuns(); startPoll(); });
onUnmounted(stopPoll);
</script>
