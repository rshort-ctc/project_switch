import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusBadge } from "@/components/status-badge";
import { getTasks } from "@/lib/api";

export default async function TasksPage() {
  const tasks = await getTasks();

  return (
    <>
      <PageHeader
        eyebrow="Tasks"
        title="Coding Tasks"
        description="Task state is reported from the backend. The dashboard does not run workflows directly."
      />
      <Panel title="Task Queue">
        {tasks.length === 0 ? (
          <EmptyState>No tasks have been created.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Repository</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td>
                    <Link href={`/tasks/${task.id}`}>{task.title}</Link>
                    <div className="muted">{task.description}</div>
                    <div className="mono muted">{task.id}</div>
                  </td>
                  <td>
                    <StatusBadge value={task.status} />
                  </td>
                  <td className="mono">{task.repository_id}</td>
                  <td className="mono">{task.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  );
}
