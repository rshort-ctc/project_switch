import "server-only";

import type {
  AgentRun,
  ApprovalRequest,
  AskContext,
  AuditEvent,
  ChatMessage,
  ChatCodeRunRequest,
  ChatCodeRunResponse,
  ChatResponse,
  HealthDetails,
  ModelGatewayHealth,
  ModelCatalog,
  ModelRoles,
  RepoStatus,
  Repository,
  Task,
  ValidationRun,
} from "./types";

const DEFAULT_API_URL = "http://127.0.0.1:8000";
const ERROR_STATUS = 400;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export function apiBaseUrl(): string {
  return (process.env.SWITCH_API_URL ?? DEFAULT_API_URL).replace(/\/$/, "");
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>("GET", path);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiRequest<T>("POST", path, body);
}

export async function apiRequest<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (response.status >= ERROR_STATUS) {
    throw new ApiError(await response.text(), response.status);
  }
  return (await response.json()) as T;
}

export async function safeGet<T>(path: string): Promise<T | null> {
  try {
    return await apiGet<T>(path);
  } catch {
    return null;
  }
}

export async function getRepositories(): Promise<Repository[]> {
  const payload = await apiGet<{ repositories: Repository[] }>("/repos");
  return payload.repositories;
}

export async function getRepoStatus(repositoryId: string): Promise<RepoStatus> {
  return apiGet<RepoStatus>(`/repos/${repositoryId}/status`);
}

export async function getTasks(): Promise<Task[]> {
  const payload = await apiGet<{ tasks: Task[] }>("/tasks");
  return payload.tasks;
}

export async function getTaskStatus(taskId: string): Promise<{
  task: Task;
  run: AgentRun | null;
}> {
  return apiGet(`/tasks/${taskId}`);
}

export async function getTaskLogs(taskId: string): Promise<AuditEvent[]> {
  const payload = await apiGet<{ events: AuditEvent[] }>(`/tasks/${taskId}/logs`);
  return payload.events;
}

export async function getTaskDiff(taskId: string): Promise<{
  diff: string;
  changed_files: string[];
}> {
  return apiGet(`/tasks/${taskId}/diff`);
}

export async function getTaskValidations(taskId: string): Promise<ValidationRun[]> {
  const payload = await apiGet<{ validations: ValidationRun[] }>(`/tasks/${taskId}/validations`);
  return payload.validations;
}

export async function getApprovals(): Promise<ApprovalRequest[]> {
  return apiGet<ApprovalRequest[]>("/approvals/pending");
}

export async function getAuditEvents(limit = 100): Promise<AuditEvent[]> {
  const payload = await apiGet<{ events: AuditEvent[] }>(`/audit?limit=${limit}`);
  return payload.events;
}

export async function getHealth(): Promise<HealthDetails | null> {
  return safeGet<HealthDetails>("/health/details");
}

export async function getModelRoles(): Promise<ModelRoles | null> {
  return safeGet<ModelRoles>("/agent/models");
}

export async function getModelGatewayHealth(): Promise<ModelGatewayHealth | null> {
  return safeGet<ModelGatewayHealth>("/model-gateway/health");
}

export async function getModelCatalog(): Promise<ModelCatalog | null> {
  return safeGet<ModelCatalog>("/model-gateway/catalog");
}

export async function askRepo(repositoryId: string, question: string): Promise<AskContext[]> {
  const payload = await apiPost<{ contexts: AskContext[] }>("/ask", {
    repository_id: repositoryId,
    question,
    max_bundles: 6,
  });
  return payload.contexts;
}

export async function sendChatMessage(input: {
  repositoryId: string | null;
  messages: ChatMessage[];
  modelRole: string;
  provider: string;
  model: string | null;
  maxBundles: number;
}): Promise<ChatResponse> {
  return apiPost<ChatResponse>("/chat", {
    repository_id: input.repositoryId,
    messages: input.messages,
    model_role: input.modelRole,
    provider: input.provider,
    model: input.model,
    max_bundles: input.maxBundles,
  });
}

export async function runChatCode(input: ChatCodeRunRequest): Promise<ChatCodeRunResponse> {
  return apiPost<ChatCodeRunResponse>("/chat/code/run", input);
}
