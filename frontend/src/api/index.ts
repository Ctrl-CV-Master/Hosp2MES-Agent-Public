import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL || "/api";

const http = axios.create({ baseURL, timeout: 30000 });

export interface DashboardSummary {
  today_tasks: number;
  completed: number;
  in_progress: number;
  anomalies: number;
  completion_rate: number;
  recent_orders: any[];
}

export interface Material {
  id: number;
  material_code: string;
  material_name: string;
  material_type: string;
  unit: string;
  specification: string;
  status: string;
}

export interface BOMItem {
  id?: number;
  material_code: string;
  quantity: number;
}
export interface BOM {
  id: number;
  bom_code: string;
  product: string;
  version: string;
  route: string;
  status: string;
  materials: BOMItem[];
}

export interface ProductionOrder {
  id: number;
  order_code: string;
  product: string;
  batch: string;
  quantity: number;
  status: string;
  created_at: string;
  stages: any[];
}

export interface Anomaly {
  id: number;
  type: string;
  target: string;
  message: string;
  active: boolean;
  created_at: string;
}

export interface AgentRun {
  id: number;
  task_id: string;
  goal: string;
  mode: string;
  status: string;
  step_count: number;
  recovery_count: number;
  current_subgoal: string;
  completed_subgoals: string[];
  pending_subgoals: string[];
  failed_subgoals: string[];
  last_action: string;
  last_evidence: any;
  success: boolean | null;
  final_verification: string;
  trace: any[];
}

export const api = {
  health: () => http.get("/health"),
  dashboard: () => http.get<DashboardSummary>("/dashboard"),

  listMaterials: (q?: string) => http.get<Material[]>("/materials", { params: { q } }),
  createMaterial: (data: Partial<Material>) => http.post<Material>("/materials", data),
  updateMaterial: (id: number, data: Partial<Material>) => http.put<Material>(`/materials/${id}`, data),
  deleteMaterial: (id: number) => http.delete(`/materials/${id}`),

  listBoms: (product?: string) => http.get<BOM[]>("/boms", { params: { product } }),
  createBom: (data: any) => http.post<BOM>("/boms", data),
  addBomItem: (id: number, item: BOMItem) => http.post<BOM>(`/boms/${id}/materials`, item),
  removeBomItem: (id: number, itemId: number) => http.delete<BOM>(`/boms/${id}/materials/${itemId}`),

  listOrders: (product?: string) => http.get<ProductionOrder[]>("/orders", { params: { product } }),
  createOrder: (data: any) => http.post<ProductionOrder>("/orders", data),
  startOrder: (id: number) => http.post<ProductionOrder>(`/orders/${id}/start`),
  getStages: (id: number) => http.get<any[]>(`/orders/${id}/stages`),
  completeStage: (id: number, stage: string, action = "complete") =>
    http.post<any>(`/orders/${id}/stages/${stage}`, { action }),

  listAnomalies: () => http.get<Anomaly[]>("/anomalies"),
  createAnomaly: (data: Partial<Anomaly>) => http.post<Anomaly>("/anomalies", data),
  resolveAnomaly: (id: number) => http.post(`/anomalies/${id}/resolve`),

  listAgentRuns: () => http.get<AgentRun[]>("/agent/runs"),
  getAgentRun: (id: number) => http.get<AgentRun>(`/agent/runs/${id}`),
  createAgentRun: (task_id: string, goal: string, mode: string) =>
    http.post<AgentRun>("/agent/runs", { task_id, goal, mode }),
};

export default api;
