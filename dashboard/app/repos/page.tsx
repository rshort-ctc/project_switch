import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { RepoAddForm } from "@/components/repo-add-form";
import { StatusBadge } from "@/components/status-badge";
import { getRepositories } from "@/lib/api";

export default async function ReposPage() {
  const repos = await getRepositories();

  return (
    <>
      <PageHeader
        eyebrow="Repositories"
        title="Registered Repos"
        description="Local source roots known to the backend. Indexing and task execution remain backend-controlled."
      />
      <Panel title="Repo Inventory">
        <RepoAddForm />
        {repos.length === 0 ? (
          <EmptyState>No repositories have been registered.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Path</th>
                <th>Branch</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {repos.map((repo) => (
                <tr key={repo.id}>
                  <td>
                    <Link href={`/repos/${repo.id}`}>{repo.name}</Link>
                    <div className="mono muted">{repo.id}</div>
                  </td>
                  <td className="mono">{repo.local_path}</td>
                  <td className="mono">{repo.default_branch}</td>
                  <td>
                    <StatusBadge value={repo.is_active} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  );
}
