// API Client - FastAPI backend ile iletişim
import type {
    AgentStatus,
    HealthStatus,
    PendingAction,
    PendingComment,
    ActionHistory,
    TaskType,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T | null> {
    try {
        const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

async function post<T>(path: string): Promise<T | null> {
    try {
        const res = await fetch(`${BASE}${path}`, {
            method: "POST",
            cache: "no-store",
        });
        return await res.json();
    } catch {
        return null;
    }
}

export const api = {
    getStatus: () => get<AgentStatus>("/"),
    getHealth: () => get<HealthStatus>("/health"),
    getStats: () => get<AgentStatus>("/agent/stats"),
    getPendingActions: () => get<PendingAction[]>("/agent/pending-actions"),
    getPendingComments: () => get<PendingComment[]>("/agent/pending-comments"),
    getActions: (limit = 25) => get<ActionHistory[]>(`/agent/actions?limit=${limit}`),
    approveAction: (id: number) => post<{ message: string }>(`/agent/approve-action/${id}`),
    rejectAction: (id: number) => post<{ message: string }>(`/agent/reject-action/${id}`),
    approveComment: (id: number) => post<{ message: string }>(`/agent/approve-comment/${id}`),
    rejectComment: (id: number) => post<{ message: string }>(`/agent/reject-comment/${id}`),
    triggerTask: (type: TaskType) => post<{ message: string }>(`/agent/trigger?task_type=${type}`),
};
