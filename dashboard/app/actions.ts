"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiPost, runChatCode, runChatTerminal, sendChatMessage } from "@/lib/api";
import { requireHostSurface } from "@/lib/surface";
import type {
  ApprovalRequest,
  ChatCodeRunRequest,
  ChatCodeRunResponse,
  ChatMessage,
  ChatResponse,
  ChatTerminalRunRequest,
  ChatTerminalRunResponse,
  Repository,
} from "@/lib/types";

export type RepoAddState = {
  error: string | null;
  repositoryId: string | null;
};

export async function addRepository(
  _previousState: RepoAddState,
  formData: FormData,
): Promise<RepoAddState> {
  const path = requiredFormValue(formData, "local_path");
  const name = optionalFormValue(formData, "name") ?? path.replace(/\/$/, "").split("/").at(-1) ?? path;
  const defaultBranch = optionalFormValue(formData, "default_branch") ?? "main";
  try {
    const repository = await apiPost<Repository>("/repos", {
      name,
      local_path: path,
      default_branch: defaultBranch,
    });
    revalidatePath("/repos");
    revalidatePath("/chat");
    return { error: null, repositoryId: repository.id };
  } catch (error) {
    return { error: readableActionError(error), repositoryId: null };
  }
}

export async function approveApproval(formData: FormData): Promise<void> {
  requireHostSurface("Approval decisions");
  const approvalId = requiredFormValue(formData, "approval_id");
  const userId = requiredFormValue(formData, "user_id");
  const note = optionalFormValue(formData, "note");
  await apiPost<ApprovalRequest>(`/approvals/${approvalId}/approve`, {
    decided_by_user_id: userId,
    decision_note: note,
  });
  revalidateDashboard();
}

export async function denyApproval(formData: FormData): Promise<void> {
  requireHostSurface("Approval decisions");
  const approvalId = requiredFormValue(formData, "approval_id");
  const userId = requiredFormValue(formData, "user_id");
  const note = optionalFormValue(formData, "note") ?? "Denied from dashboard";
  await apiPost<ApprovalRequest>(`/approvals/${approvalId}/deny`, {
    decided_by_user_id: userId,
    decision_note: note,
  });
  revalidateDashboard();
}

export async function sendDashboardChatMessage(input: {
  repositoryId: string | null;
  messages: ChatMessage[];
  modelRole: string;
  provider: string;
  model: string | null;
  maxBundles: number;
}): Promise<ChatResponse> {
  return sendChatMessage(input);
}

export async function runDashboardCode(input: ChatCodeRunRequest): Promise<ChatCodeRunResponse> {
  try {
    requireHostSurface("Python sandbox console");
    return await runChatCode(input);
  } catch (error) {
    return {
      language: input.language,
      exit_code: null,
      stdout: "",
      stderr: readableActionError(error),
      duration_ms: 0,
      timed_out: false,
      truncated: false,
      network_enabled: false,
    };
  }
}

export async function runDashboardTerminal(
  input: ChatTerminalRunRequest,
): Promise<ChatTerminalRunResponse> {
  try {
    requireHostSurface("Terminal");
    return await runChatTerminal(input);
  } catch (error) {
    return {
      repository_id: input.repository_id,
      command: input.command,
      argv: [],
      category: "terminal",
      exit_code: null,
      stdout: "",
      stderr: readableActionError(error),
      duration_ms: 0,
      timed_out: false,
      truncated: false,
      network_enabled: false,
    };
  }
}

function readableActionError(error: unknown): string {
  if (error instanceof ApiError) {
    return extractApiDetail(error.message) ?? `Backend returned HTTP ${error.status}`;
  }
  return error instanceof Error ? error.message : "Code execution failed.";
}

function extractApiDetail(message: string): string | null {
  try {
    const parsed = JSON.parse(message) as { detail?: unknown };
    return typeof parsed.detail === "string" ? parsed.detail : null;
  } catch {
    return message;
  }
}

function requiredFormValue(formData: FormData, key: string): string {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`missing form value: ${key}`);
  }
  return value;
}

function optionalFormValue(formData: FormData, key: string): string | null {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }
  return value;
}

function revalidateDashboard(): void {
  revalidatePath("/");
  revalidatePath("/approvals");
  revalidatePath("/audit");
  revalidatePath("/tasks");
}
