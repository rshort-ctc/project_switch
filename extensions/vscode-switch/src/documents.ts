import * as vscode from "vscode";

export async function showMarkdown(title: string, content: string): Promise<void> {
  const document = await vscode.workspace.openTextDocument({
    content,
    language: "markdown",
  });
  await vscode.window.showTextDocument(document, {
    preview: true,
    viewColumn: vscode.ViewColumn.Beside,
  });
  void title;
}

export async function showDiffDocument(content: string): Promise<void> {
  const document = await vscode.workspace.openTextDocument({
    content: content || "No diff available.",
    language: "diff",
  });
  await vscode.window.showTextDocument(document, {
    preview: true,
    viewColumn: vscode.ViewColumn.Beside,
  });
}

export async function openWorkspaceFile(
  repositoryPath: string,
  filePath: string,
  line: number,
): Promise<void> {
  const uri = vscode.Uri.file(joinPath(repositoryPath, filePath));
  const document = await vscode.workspace.openTextDocument(uri);
  const editor = await vscode.window.showTextDocument(document, { preview: true });
  const position = new vscode.Position(Math.max(line - 1, 0), 0);
  editor.selection = new vscode.Selection(position, position);
  editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenter);
}

function joinPath(root: string, relativePath: string): string {
  return vscode.Uri.joinPath(vscode.Uri.file(root), ...relativePath.split("/")).fsPath;
}
