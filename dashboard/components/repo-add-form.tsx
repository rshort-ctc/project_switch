"use client";

import { FolderOpen, FolderPlus, Loader2 } from "lucide-react";
import { useActionState, useRef, useState, useSyncExternalStore } from "react";

import { addRepository, type RepoAddState } from "@/app/actions";

const INITIAL_STATE: RepoAddState = {
  error: null,
  repositoryId: null,
};

function subscribeToRuntimeChanges() {
  return () => {};
}

function getBrowserSnapshot() {
  return (
    typeof window !== "undefined" &&
    ("isTauri" in globalThis || "__TAURI_INTERNALS__" in window)
  );
}

function getServerSnapshot() {
  return false;
}

export function RepoAddForm() {
  const [state, action, isPending] = useActionState(addRepository, INITIAL_STATE);
  const [path, setPath] = useState("");
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [browseError, setBrowseError] = useState<string | null>(null);
  const directoryInputRef = useRef<HTMLInputElement>(null);
  const canBrowse = useSyncExternalStore(
    subscribeToRuntimeChanges,
    getBrowserSnapshot,
    getServerSnapshot,
  );

  async function browseForRepository() {
    setIsBrowsing(true);
    setBrowseError(null);
    try {
      if (canBrowse) {
        const { invoke } = await import("@tauri-apps/api/core");
        const selectedPath = await invoke<string | null>("pick_repository_directory");
        if (selectedPath) {
          setPath(selectedPath);
        }
        return;
      }
      await browseForDirectoryInBrowser();
    } catch (error) {
      setBrowseError(error instanceof Error ? error.message : "Unable to open directory picker.");
    } finally {
      setIsBrowsing(false);
    }
  }

  async function browseForDirectoryInBrowser() {
    const browserWindow = window as Window & {
      showDirectoryPicker?: () => Promise<{ name: string }>;
    };
    if (browserWindow.showDirectoryPicker) {
      const directory = await browserWindow.showDirectoryPicker();
      setBrowseError(
        `Selected "${directory.name}", but browsers do not expose the absolute path SWITCH needs. Use the desktop app or paste the path.`,
      );
      return;
    }
    directoryInputRef.current?.click();
  }

  function handleBrowserDirectorySelected() {
    const directoryName = directoryInputRef.current?.files?.[0]?.webkitRelativePath.split("/")[0];
    if (directoryName) {
      setBrowseError(
        `Selected "${directoryName}", but browsers do not expose the absolute path SWITCH needs. Use the desktop app or paste the path.`,
      );
    }
  }

  return (
    <form action={action} className="repo-add-form">
      <input className="input" name="name" placeholder="Name" />
      <div className="path-picker">
        <input
          ref={directoryInputRef}
          className="hidden-file-input"
          onChange={handleBrowserDirectorySelected}
          type="file"
          // @ts-expect-error Chromium directory picking is intentionally non-standard.
          webkitdirectory=""
        />
        <input
          className="input"
          name="local_path"
          onChange={(event) => setPath(event.target.value)}
          placeholder="/absolute/path/to/local/repo"
          required
          value={path}
        />
        <button
          aria-label="Browse for repository directory"
          className="icon-button"
          disabled={isBrowsing}
          onClick={browseForRepository}
          title="Browse for repository directory"
          type="button"
        >
          {isBrowsing ? <Loader2 size={16} /> : <FolderOpen size={16} />}
        </button>
      </div>
      <input className="input compact" defaultValue="main" name="default_branch" placeholder="Branch" />
      <button className="button" disabled={isPending} type="submit">
        {isPending ? <Loader2 size={16} /> : <FolderPlus size={16} />}
        Add
      </button>
      {browseError ? <p className="form-message error">{browseError}</p> : null}
      {state.error ? <p className="form-message error">{state.error}</p> : null}
      {state.repositoryId ? <p className="form-message">Registered repo {state.repositoryId}</p> : null}
    </form>
  );
}
