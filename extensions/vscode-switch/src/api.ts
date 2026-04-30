import { validateLocalBackendUrl } from "./locality";
import type {
  ApprovalRequest,
  AskResponse,
  AuditEvent,
  HealthDetails,
  ModelRoles,
  RepoIndex,
  RepoStatus,
  Repository,
  Task,
  TaskApplyPatchResponse,
  TaskCreateResponse,
  TaskDiff,
  TaskStatus,
  ValidationRun,
} from "./types";

const HTTP_ERROR_STATUS = 400;

export class SwitchApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
  }
}

export class SwitchApiClient {
  constructor(private readonly apiUrl: string) {}

  async health(): Promise<HealthDetails> {
    return this.get<HealthDetails>("/health/details");
  }

  async models(): Promise<ModelRoles> {
    return this.get<ModelRoles>("/agent/models");
  }

  async listRepositories(): Promise<Repository[]> {
    const payload = await this.get<{ repositories: Repository[] }>("/repos");
    return payload.repositories;
  }

  async addRepository(input: {
    name: string;
    local_path: string;
    default_branch: string;
  }): Promise<Repository> {
    return this.post<Repository>("/repos", input);
  }

  async indexRepository(repositoryId: string): Promise<RepoIndex> {
    return this.post<RepoIndex>(`/repos/${encodeURIComponent(repositoryId)}/index`);
  }

  async repositoryStatus(repositoryId: string): Promise<RepoStatus> {
    return this.get<RepoStatus>(`/repos/${encodeURIComponent(repositoryId)}/status`);
  }

  async ask(repositoryId: string, question: string, maxBundles: number): Promise<AskResponse> {
    return this.post<AskResponse>("/ask", {
      repository_id: repositoryId,
      question,
      max_bundles: maxBundles,
    });
  }

  async createTask(input: {
    repository_id: string;
    created_by_user_id: string;
    title: string;
    description: string;
  }): Promise<TaskCreateResponse> {
    return this.post<TaskCreateResponse>("/tasks", input);
  }

  async listTasks(): Promise<Task[]> {
    const payload = await this.get<{ tasks: Task[] }>("/tasks");
    return payload.tasks;
  }

  async taskStatus(taskId: string): Promise<TaskStatus> {
    return this.get<TaskStatus>(`/tasks/${encodeURIComponent(taskId)}`);
  }

  async taskDiff(taskId: string): Promise<TaskDiff> {
    return this.get<TaskDiff>(`/tasks/${encodeURIComponent(taskId)}/diff`);
  }

  async applyApprovedPatch(input: {
    taskId: string;
    actorUserId: string;
    approvalRequestId: string;
    unifiedDiff: string;
  }): Promise<TaskApplyPatchResponse> {
    return this.post<TaskApplyPatchResponse>(
      `/tasks/${encodeURIComponent(input.taskId)}/apply-approved-patch`,
      {
        actor_user_id: input.actorUserId,
        approval_request_id: input.approvalRequestId,
        unified_diff: input.unifiedDiff,
      },
    );
  }

  async taskValidations(taskId: string): Promise<ValidationRun[]> {
    const payload = await this.get<{ validations: ValidationRun[] }>(
      `/tasks/${encodeURIComponent(taskId)}/validations`,
    );
    return payload.validations;
  }

  async taskLogs(taskId: string): Promise<AuditEvent[]> {
    const payload = await this.get<{ events: AuditEvent[] }>(
      `/tasks/${encodeURIComponent(taskId)}/logs`,
    );
    return payload.events;
  }

  async pendingApprovals(): Promise<ApprovalRequest[]> {
    return this.get<ApprovalRequest[]>("/approvals/pending");
  }

  async approve(approvalId: string, userId: string, note: string | null): Promise<ApprovalRequest> {
    return this.post<ApprovalRequest>(`/approvals/${encodeURIComponent(approvalId)}/approve`, {
      decided_by_user_id: userId,
      decision_note: note,
    });
  }

  async deny(approvalId: string, userId: string, note: string | null): Promise<ApprovalRequest> {
    return this.post<ApprovalRequest>(`/approvals/${encodeURIComponent(approvalId)}/deny`, {
      decided_by_user_id: userId,
      decision_note: note,
    });
  }

  async audit(limit = 100): Promise<AuditEvent[]> {
    const payload = await this.get<{ events: AuditEvent[] }>(`/audit?limit=${limit}`);
    return payload.events;
  }

  private async get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  private async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("POST", path, body);
  }

  private async request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const baseUrl = validateLocalBackendUrl(this.apiUrl);
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status >= HTTP_ERROR_STATUS) {
      throw new SwitchApiError(await errorText(response), response.status);
    }
    return (await response.json()) as T;
  }
}

async function errorText(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    return typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload);
  } catch {
    return `SWITCH backend returned HTTP ${response.status}`;
  }
}
