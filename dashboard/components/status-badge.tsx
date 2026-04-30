type StatusBadgeProps = {
  value: string | number | boolean | null | undefined;
  tone?: "default" | "success" | "warning" | "danger" | "info";
};

export function StatusBadge({ value, tone }: StatusBadgeProps) {
  const text = String(value ?? "unknown");
  const resolvedTone = tone ?? statusTone(text);
  return <span className={`badge ${resolvedTone === "default" ? "" : resolvedTone}`}>{text}</span>;
}

export function RiskBadge({ risk }: { risk: string }) {
  const tone = risk === "high" || risk === "critical" ? "danger" : risk === "low" ? "info" : "warning";
  return <StatusBadge value={risk} tone={tone} />;
}

function statusTone(value: string): StatusBadgeProps["tone"] {
  const normalized = value.toLowerCase();
  if (["ok", "ready", "completed", "approved", "passed", "true"].includes(normalized)) {
    return "success";
  }
  if (["pending", "running", "waiting_approval", "open"].includes(normalized)) {
    return "warning";
  }
  if (["failed", "rejected", "denied", "error", "false"].includes(normalized)) {
    return "danger";
  }
  return "default";
}
