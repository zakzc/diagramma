import type { components } from "./schema";
import type { RepoInput } from "./repoInput";

export type Health = components["schemas"]["Health"];
export type DiagramRecord = components["schemas"]["DiagramRecord"];
export type DiagramSummary = components["schemas"]["DiagramSummary"];
export type DiagramCreated = components["schemas"]["DiagramCreated"];

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function failure(r: Response): Promise<ApiError> {
  try {
    const body = await r.json();
    if (body?.error) return new ApiError(body.error.code, body.error.message);
  } catch {
    /* fall through */
  }
  return new ApiError("HTTP_ERROR", `Request failed (${r.status})`);
}

export async function getHealth(): Promise<Health> {
  const r = await fetch("/api/health");
  if (!r.ok) throw await failure(r);
  return r.json();
}

export async function createDiagram(input: RepoInput): Promise<DiagramCreated> {
  const r = await fetch("/api/diagrams", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw await failure(r);
  return r.json();
}

export async function getDiagram(id: string): Promise<DiagramRecord> {
  const r = await fetch(`/api/diagrams/${id}`);
  if (!r.ok) throw await failure(r);
  return r.json();
}

export async function listDiagrams(): Promise<DiagramSummary[]> {
  const r = await fetch("/api/diagrams");
  if (!r.ok) throw await failure(r);
  return r.json();
}

export async function deleteDiagram(id: string): Promise<void> {
  const r = await fetch(`/api/diagrams/${id}`, { method: "DELETE" });
  if (!r.ok) throw await failure(r);
}

export type EditFormat = "c4" | "flowchart";
export type DiagramView = components["schemas"]["DiagramView"];

/** The diagram as `format` rolled up to `depth`, plus the saved edit for that exact view. */
export async function getView(id: string, format: EditFormat, depth: number): Promise<DiagramView> {
  const r = await fetch(`/api/diagrams/${id}/views/${format}/${depth}`);
  if (!r.ok) throw await failure(r);
  return r.json();
}

export async function saveEdit(
  id: string,
  format: EditFormat,
  depth: number,
  text: string,
): Promise<DiagramView> {
  const r = await fetch(`/api/diagrams/${id}/edits/${format}/${depth}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw await failure(r);
  return r.json();
}

export async function discardEdit(id: string, format: EditFormat, depth: number): Promise<DiagramView> {
  const r = await fetch(`/api/diagrams/${id}/edits/${format}/${depth}`, { method: "DELETE" });
  if (!r.ok) throw await failure(r);
  return r.json();
}
