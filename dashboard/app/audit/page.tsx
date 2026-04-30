import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { getAuditEvents } from "@/lib/api";

export default async function AuditPage() {
  const events = await getAuditEvents(200);

  return (
    <>
      <PageHeader
        eyebrow="Audit"
        title="Audit Log"
        description="Durable backend audit events for users, repos, tasks, runs, approvals, tools, and policy decisions."
      />
      <Panel title="Recent Events">
        {events.length === 0 ? (
          <EmptyState>No audit events recorded.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Event</th>
                <th>Summary</th>
                <th>Subject</th>
                <th>Run</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td className="mono">{event.created_at}</td>
                  <td className="mono">{event.event_type}</td>
                  <td>{event.summary}</td>
                  <td className="mono">
                    {event.subject_type}:{event.subject_id ?? "none"}
                  </td>
                  <td className="mono">{event.agent_run_id ?? "none"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  );
}
