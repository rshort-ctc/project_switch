"use server";

import { revalidatePath } from "next/cache";

import { apiPost, sendChatMessage } from "@/lib/api";
import type { ApprovalRequest, ChatMessage, ChatResponse } from "@/lib/types";

export async function approveApproval(formData: FormData): Promise<void> {
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
  maxBundles: number;
}): Promise<ChatResponse> {
  return sendChatMessage(input);
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
