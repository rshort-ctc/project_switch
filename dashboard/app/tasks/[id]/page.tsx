import Link from "next/link";
import { notFound } from "next/navigation";

import { DiffViewer } from "@/components/diff-viewer";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusBadge } from "@/components/status-badge";
import { getTaskDiff, getTaskLogs, getTaskStatus, getTaskValidations } from "@/lib/api";

type TaskDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default async function TaskDetailPage({ params }: TaskDetailPageProps) {
  const { id } = await params;
  const status = await getTaskStatus(id).catch(() => null);
  if (status === null) {
    notFound();
  }
  const [logs, diff, validations] = await Promise.all([
    getTaskLogs(id),
    getTaskDiff(id),
    getTaskValidations(id),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Task"
        title={status.task.title}
        description={status.task.description}
        action={<Link href="/tasks">Back to tasks</Link>}
      />
      <div className="grid cols-2">
        <Panel title="Run Timeline">
          <div className="stack">
            <div>
              Task <StatusBadge value={status.task.status} />
            </div>
            {status.run === null ? (
              <EmptyState>No agent run has been created.</EmptyState>
            ) : (
              <div className="timeline-item">
                <div>
                  Run <StatusBadge value={status.run.status} />
                </div>
                <div className="mono muted">{status.run.id}</div>
                <div className="muted">
                  base={status.run.base_branch} target={status.run.target_branch ?? "not set"}
                </div>
              </div>
            )}
            {logs.map((event) => (
              <div className="timeline-item" key={event.id}>
                <div className="mono">{event.event_type}</div>
                <div>{event.summary}</div>
                <div className="muted">{event.created_at}</div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Validation Results">
          {validations.length === 0 ? (
            <EmptyState>No validation runs recorded.</EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Command</th>
                  <th>Status</th>
                  <th>Exit</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {validations.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <span className="mono">{run.command}</span>
                      {run.output_summary ? <div className="muted">{run.output_summary}</div> : null}
                    </td>
                    <td>
                      <StatusBadge value={run.status} />
                    </td>
                    <td>{run.exit_code ?? "not set"}</td>
                    <td>{run.duration_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <div style={{ marginTop: 14 }}>
        <Panel title="Diff Viewer">
          <DiffViewer changedFiles={diff.changed_files} diff={diff.diff} />
        </Panel>
      </div>
    </>
  );
}
