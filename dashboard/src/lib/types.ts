// TypeScript type tanımları - API yanıtları

export interface AgentStats {
    cycles_completed: number;
    repos_discovered: number;
    issues_analyzed: number;
    discussions_analyzed: number;
    prs_created: number;
    comments_generated: number;
}

export interface AgentStatus {
    message: string;
    status: string;
    stats: AgentStats;
}

export interface HealthStatus {
    agent: string;
    database: string;
    ollama: string;
    github: string;
    docker: string;
    chromadb: string;
}

export interface PatchInfo {
    file: string;
    diff: string | null;
    content_preview: string;
}

export interface PendingAction {
    id: number;
    repo: string;
    action_type: string;
    branch: string | null;
    commit_message: string | null;
    sandbox_test: boolean | null;
    details: Record<string, unknown> | null;
    patches: PatchInfo[];
    created_at: string;
}

export interface PendingComment {
    id: number;
    repo: string;
    type: string;
    target_number: number;
    target_url: string | null;
    body_preview: string;
    created_at: string;
}

export interface ActionHistory {
    id: number;
    repo: string;
    action_type: string;
    status: string;
    pr_url: string | null;
    details: Record<string, unknown> | null;
    created_at: string;
    completed_at: string | null;
}

export type TaskType =
    | "trend_hunt"
    | "repo_setup"
    | "community_support"
    | "discussion_support"
    | "issue_solving";
