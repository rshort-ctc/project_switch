import Link from "next/link";
import { AlertTriangle, CheckCircle2, MessageSquare, Server } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { RiskBadge, StatusBadge } from "@/components/status-badge";
import {
  getApprovals,
  getAuditEvents,
  getHealth,
  getModelGatewayHealth,
  getModelRoles,
  getRepositories,
  getTasks,
} from "@/lib/api";

export default async function DashboardHome() {
  const [repos, tasks, approvals, auditEvents, health, modelRoles, modelGateway] = await Promise.all([
    getRepositories(),
    getTasks(),
    getApprovals(),
    getAuditEvents(8),
    getHealth(),
    getModelRoles(),
    getModelGatewayHealth(),
  ]);
  const failedTasks = tasks.filter((task) => task.status === "failed").length;

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Dashboard"
        description="Visibility across local repositories, agent tasks, approvals, validation, and audit events."
      />

      <div className="grid cols-3">
        <div className="panel metric">
          <span className="muted">Repositories</span>
          <span className="metric-value">{repos.length}</span>
        </div>
        <div className="panel metric">
          <span className="muted">Tasks</span>
          <span className="metric-value">{tasks.length}</span>
        </div>
        <div className="panel metric">
          <span className="muted">Pending approvals</span>
          <span className="metric-value">{approvals.length}</span>
        </div>
      </div>

      <div className="panel chat-entry">
        <div>
          <MessageSquare aria-hidden="true" size={20} />
          <strong>Open SWITCH Chat</strong>
          <span className="muted">Repo-aware local assistant with citations, task handoff, and approvals.</span>
        </div>
        <Link className="button-link" href="/chat">
          Launch chat
        </Link>
      </div>

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <Panel title="Model and Server Health">
          <div className="stack">
            <div>
              <Server aria-hidden="true" size={16} /> Backend{" "}
              <StatusBadge value={health?.status ?? "unavailable"} />
              <span className="muted"> LOCAL_ONLY={String(health?.local_only ?? "unknown")}</span>
            </div>
            <div>
              <Server aria-hidden="true" size={16} /> Model gateway{" "}
              <StatusBadge value={modelGateway?.status ?? "unavailable"} />
              <span className="muted"> models={modelGateway?.model_count ?? 0}</span>
            </div>
            <table className="table">
              <tbody>
                {Object.entries(modelRoles ?? {}).map(([role, model]) => (
                  <tr key={role}>
                    <th>{role}</th>
                    <td className="mono">{model ?? "not configured"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Risk Queue" action={<Link href="/approvals">Open queue</Link>}>
          {approvals.length === 0 ? (
            <EmptyState>No pending approvals.</EmptyState>
          ) : (
            <div className="stack">
              {approvals.slice(0, 5).map((approval) => (
                <div className="timeline-item" key={approval.id}>
                  <RiskBadge risk={approval.risk_level} />{" "}
                  <Link className="mono" href="/approvals">
                    {approval.requested_action}
                  </Link>
                  <div className="muted">{approval.reason}</div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <Panel title="Task Health" action={<Link href="/tasks">View tasks</Link>}>
          <div className="stack">
            <div>
              <CheckCircle2 aria-hidden="true" size={16} /> Active tasks{" "}
              <StatusBadge value={tasks.length - failedTasks} tone="info" />
            </div>
            <div>
              <AlertTriangle aria-hidden="true" size={16} /> Failed tasks{" "}
              <StatusBadge value={failedTasks} tone={failedTasks > 0 ? "danger" : "success"} />
            </div>
          </div>
        </Panel>

        <Panel title="Recent Audit Events" action={<Link href="/audit">Full audit</Link>}>
          {auditEvents.length === 0 ? (
            <EmptyState>No audit events recorded.</EmptyState>
          ) : (
            <div className="timeline">
              {auditEvents.map((event) => (
                <div className="timeline-item" key={event.id}>
                  <div className="mono">{event.event_type}</div>
                  <div>{event.summary}</div>
                  <div className="muted">{event.created_at}</div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
