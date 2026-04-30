import * as vscode from "vscode";

import { DEFAULT_API_URL, normalizeApiUrl } from "./locality";

export type ExtensionConfig = {
  apiUrl: string;
  localUserId: string;
  selectedRepositoryId: string;
  defaultBranch: string;
  maxAskBundles: number;
};

export function getConfig(): ExtensionConfig {
  const config = vscode.workspace.getConfiguration("switch");
  return {
    apiUrl: normalizeApiUrl(config.get<string>("apiUrl", DEFAULT_API_URL)),
    localUserId: config.get<string>("localUserId", "").trim(),
    selectedRepositoryId: config.get<string>("selectedRepositoryId", "").trim(),
    defaultBranch: config.get<string>("defaultBranch", "main").trim() || "main",
    maxAskBundles: clamp(config.get<number>("maxAskBundles", 6), 1, 20),
  };
}

export async function setSelectedRepository(repositoryId: string): Promise<void> {
  await vscode.workspace
    .getConfiguration("switch")
    .update("selectedRepositoryId", repositoryId, vscode.ConfigurationTarget.Workspace);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
