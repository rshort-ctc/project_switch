import type {
  ApprovalRequest,
  AskResponse,
  AuditEvent,
  HealthDetails,
  TaskDiff,
  TaskStatus,
  ValidationRun,
} from "./types";

export function renderAskMarkdown(response: AskResponse): string {
  const lines = [`# SWITCH Context`, "", response.answer, ""];
  for (const context of response.contexts) {
    lines.push(
      `## ${context.path}:${context.start_line}-${context.end_line}`,
      "",
      `Score: ${context.score.toFixed(2)}`,
      "",
    );
    for (const reason of context.reasons) {
      lines.push(`- ${reason}`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

export function renderTaskMarkdown(
  status: TaskStatus,
  diff: TaskDiff,
  validations: ValidationRun[],
  events: AuditEvent[],
): string {
  const lines = [
    `# ${status.task.title}`,
    "",
    `Task: ${status.task.id}`,
    `Status: ${status.task.status}`,
    status.run ? `Run: ${status.run.id} (${status.run.status})` : "Run: not created",
    "",
    "## Validation",
    "",
  ];
  if (validations.length === 0) {
    lines.push("No validation results recorded.", "");
  } else {
    for (const validation of validations) {
      lines.push(
        `- ${validation.status} exit=${validation.exit_code ?? "n/a"} ${validation.command}`,
      );
    }
    lines.push("");
  }
  lines.push("## Changed Files", "");
  if (diff.changed_files.length === 0) {
    lines.push("No changed files reported.", "");
  } else {
    for (const file of diff.changed_files) {
      lines.push(`- ${file}`);
    }
    lines.push("");
  }
  lines.push("## Diff", "", "```diff", diff.diff || "No diff available.", "```", "");
  lines.push("## Audit Events", "");
  for (const event of events.slice(0, 25)) {
    lines.push(`- ${event.created_at} ${event.event_type}: ${event.summary}`);
  }
  return lines.join("\n");
}

export function renderApprovalMarkdown(approval: ApprovalRequest): string {
  return [
    `# Approval ${approval.id}`,
    "",
    `Action: ${approval.requested_action}`,
    `Status: ${approval.status}`,
    `Risk: ${approval.risk_level}`,
    `Task: ${approval.task_id ?? "n/a"}`,
    `Run: ${approval.agent_run_id}`,
    "",
    "## Reason",
    "",
    approval.reason,
    "",
    "## Command",
    "",
    approval.command ?? "n/a",
    "",
    "## Diff Summary",
    "",
    approval.diff_summary ?? "n/a",
  ].join("\n");
}

export function renderHealthMarkdown(health: HealthDetails): string {
  const lines = [
    "# SWITCH Backend",
    "",
    `Status: ${health.status}`,
    `Environment: ${health.environment}`,
    `LOCAL_ONLY: ${health.local_only}`,
    `Default permission level: ${health.default_permission_level}`,
    `Sandbox network enabled: ${health.sandbox_network_enabled}`,
    `Audit retention days: ${health.audit_retention_days}`,
    "",
    "## Services",
    "",
  ];
  for (const [name, service] of Object.entries(health.services)) {
    lines.push(`- ${name}: ${service.configured ? "configured" : "not configured"}`);
  }
  return lines.join("\n");
}

export function sanitizeTitle(value: string): string {
  return value.replace(/[^\w .-]/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
}
