import { FileCode } from "lucide-react";

import { EmptyState } from "./empty-state";

type DiffViewerProps = {
  diff: string;
  changedFiles: string[];
};

export function DiffViewer({ diff, changedFiles }: DiffViewerProps) {
  return (
    <div className="stack">
      <div className="stack">
        {changedFiles.length === 0 ? (
          <span className="muted">No changed files reported.</span>
        ) : (
          changedFiles.map((file) => (
            <span className="mono" key={file}>
              <FileCode aria-hidden="true" size={14} /> {file}
            </span>
          ))
        )}
      </div>
      {diff.length === 0 ? <EmptyState>No diff is available.</EmptyState> : <pre className="diff">{diff}</pre>}
    </div>
  );
}
