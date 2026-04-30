import { ApprovalActions } from "@/components/approval-actions";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { RiskBadge, StatusBadge } from "@/components/status-badge";
import { getApprovals } from "@/lib/api";

export default async function ApprovalsPage() {
  const approvals = await getApprovals();

  return (
    <>
      <PageHeader
        eyebrow="Approvals"
        title="Human Approval Queue"
        description="Risky and mutating actions pause here. Decisions are sent to the backend approval API."
      />
      <Panel title="Pending Requests">
        {approvals.length === 0 ? (
          <EmptyState>No pending approval requests.</EmptyState>
        ) : (
          <div className="stack">
            {approvals.map((approval) => (
              <section className="panel" key={approval.id}>
                <div className="panel-header">
                  <div>
                    <span className="mono">{approval.requested_action}</span>{" "}
                    <RiskBadge risk={approval.risk_level} />
                  </div>
                  <StatusBadge value={approval.status} />
                </div>
                <div className="panel-body stack">
                  <div>{approval.reason}</div>
                  <div className="mono muted">approval_id={approval.id}</div>
                  <div className="mono muted">run={approval.agent_run_id}</div>
                  {approval.task_id ? <div className="mono muted">task={approval.task_id}</div> : null}
                  {approval.command ? <div className="mono">command: {approval.command}</div> : null}
                  {approval.diff_summary ? <div>{approval.diff_summary}</div> : null}
                  <ApprovalActions approval={approval} />
                </div>
              </section>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}
