import Link from "next/link";
import { notFound } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusBadge } from "@/components/status-badge";
import { askRepo, getRepoStatus } from "@/lib/api";
import { isHostSurface } from "@/lib/surface";

type RepoDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default async function RepoDetailPage({ params }: RepoDetailPageProps) {
  const { id } = await params;
  const status = await getRepoStatus(id).catch(() => null);
  if (status === null) {
    notFound();
  }
  const showHostDiagnostics = isHostSurface();
  const contexts = showHostDiagnostics
    ? await askRepo(id, "recent task policy validation diff approval").catch(() => [])
    : [];

  return (
    <>
      <PageHeader
        eyebrow="Repository"
        title={status.repository.name}
        description={status.repository.local_path}
        action={<Link href="/repos">Back to repos</Link>}
      />
      <div className="grid cols-2">
        <Panel title="Index Status">
          {status.latest_index === null ? (
            <EmptyState>No index has been recorded for this repository.</EmptyState>
          ) : (
            <table className="table">
              <tbody>
                <tr>
                  <th>Status</th>
                  <td>
                    <StatusBadge value={status.latest_index.status} />
                  </td>
                </tr>
                <tr>
                  <th>Files</th>
                  <td>{status.latest_index.indexed_files}</td>
                </tr>
                <tr>
                  <th>Chunks</th>
                  <td>{status.latest_index.indexed_chunks}</td>
                </tr>
                <tr>
                  <th>Commit</th>
                  <td className="mono">{status.latest_index.commit_sha || "unknown"}</td>
                </tr>
              </tbody>
            </table>
          )}
        </Panel>

        {showHostDiagnostics ? (
          <Panel title="Retrieval Context Sample">
            {contexts.length === 0 ? (
              <EmptyState>No retrieval context available. Index the repo first.</EmptyState>
            ) : (
              <div className="stack">
                {contexts.map((context) => (
                  <div className="timeline-item" key={`${context.path}-${context.start_line}`}>
                    <div className="mono">
                      {context.path}:{context.start_line}-{context.end_line}
                    </div>
                    <div>score={context.score.toFixed(2)}</div>
                    <div className="muted">{context.reasons.join("; ")}</div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        ) : null}
      </div>
    </>
  );
}
