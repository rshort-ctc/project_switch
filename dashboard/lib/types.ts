export type Timestamped = {
  created_at: string;
  updated_at: string;
};

export type Repository = Timestamped & {
  id: string;
  name: string;
  local_path: string;
  default_branch: string;
  is_active: boolean;
};

export type RepoIndex = {
  repository_id: string;
  index_id: string;
  status: string;
  commit_sha: string;
  indexed_files: number;
  indexed_chunks: number;
  skipped_ignored_files: number;
  skipped_binary_files: number;
  skipped_unchanged_files: number;
};

export type RepoStatus = {
  repository: Repository;
  latest_index: RepoIndex | null;
};

export type Task = Timestamped & {
  id: string;
  repository_id: string;
  created_by_user_id: string;
  title: string;
  description: string;
  status: string;
};

export type AgentRun = Timestamped & {
  id: string;
  task_id: string;
  status: string;
  base_branch: string;
  target_branch: string | null;
  model_name: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type ApprovalRequest = Timestamped & {
  id: string;
  task_id: string | null;
  agent_run_id: string;
  requested_by_user_id: string;
  decided_by_user_id: string | null;
  status: string;
  requested_action: string;
  risk_level: string;
  reason: string;
  diff_summary: string | null;
  command: string | null;
  decision_note: string | null;
  denial_reason: string | null;
  decided_at: string | null;
};

export type AuditEvent = Timestamped & {
  id: string;
  actor_user_id: string | null;
  agent_run_id: string | null;
  event_type: string;
  summary: string;
  subject_type: string;
  subject_id: string | null;
  trace_id: string | null;
};

export type ValidationRun = Timestamped & {
  id: string;
  agent_run_id: string;
  patch_artifact_id: string | null;
  status: string;
  command: string;
  exit_code: number | null;
  duration_ms: number;
  output_summary: string | null;
};

export type AskContext = {
  path: string;
  start_line: number;
  end_line: number;
  score: number;
  reasons: string[];
};

export type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type ChatResponse = {
  answer: string;
  contexts: AskContext[];
  model: string | null;
  model_role: string;
  provider: string;
  used_model: boolean;
  degraded: boolean;
  stop_reason: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
};

export type ModelCatalog = {
  providers: string[];
  models: string[];
  models_by_provider: Record<string, string[]>;
  allow_ollama_cloud_models: boolean;
  local_only: boolean;
};

export type ChatCodeRunRequest = {
  language: "python";
  code: string;
  timeout_seconds: number;
};

export type ChatCodeRunResponse = {
  language: string;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  duration_ms: number;
  timed_out: boolean;
  truncated: boolean;
  network_enabled: boolean;
};

export type HealthDetails = {
  status: string;
  app: string;
  environment: string;
  local_only: boolean;
  audit_retention_days: number;
  default_permission_level: number;
  sandbox_network_enabled: boolean;
  services: Record<string, { configured: boolean }>;
};

export type ModelRoles = {
  planner_model: string | null;
  coder_model: string | null;
  reviewer_model: string | null;
  summarizer_model: string | null;
  embedding_model: string | null;
  reranker_model: string | null;
};

export type ModelGatewayHealth = {
  status: string;
  endpoint: string;
  model_count: number;
  local_only: boolean;
};
