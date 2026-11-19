import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { type DiagramRecord, type EditFormat, discardEdit, getView, saveEdit } from "./client";

/**
 * Editor state for one diagram. A "view" is a format at a depth, and each view has its own text:
 * unsaved draft > saved edit > generated. A draft equal to what is saved is not a draft.
 * Switching view keeps the previous one on screen (read-only) until the new text has loaded.
 */
export function useDiagramEditor(d: DiagramRecord) {
  const qc = useQueryClient();
  const [format, setFormat] = useState<EditFormat>("flowchart");
  const [depth, setDepthRaw] = useState(d.auto_depth);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const key = `${format}:${depth}`;

  const viewQ = useQuery({
    queryKey: ["view", d.id, format, depth],
    queryFn: () => getView(d.id, format, depth),
    placeholderData: keepPreviousData,
  });
  const view = viewQ.data;
  const loading = viewQ.isPending || viewQ.isPlaceholderData;
  const generated = view?.generated ?? "";
  const base = view ? (view.edited ?? view.generated) : "";
  const text = drafts[key] ?? base;

  const setText = (next: string) => {
    if (loading) return;
    setDrafts((cur) => {
      const { [key]: _old, ...rest } = cur;
      return next === base ? rest : { ...rest, [key]: next };
    });
  };
  const clearDraft = (k: string) =>
    setDrafts((cur) => {
      const { [k]: _old, ...rest } = cur;
      return rest;
    });
  const store = (v: Awaited<ReturnType<typeof getView>>) => {
    qc.setQueryData(["view", d.id, v.format, v.depth], v);
    qc.invalidateQueries({ queryKey: ["diagram", d.id] }); // saved_edits changed
    clearDraft(`${v.format}:${v.depth}`);
  };

  const save = useMutation({
    mutationFn: (v: { format: EditFormat; depth: number; text: string }) =>
      saveEdit(d.id, v.format, v.depth, v.text),
    onSuccess: store,
  });
  const discard = useMutation({
    mutationFn: (v: { format: EditFormat; depth: number }) => discardEdit(d.id, v.format, v.depth),
    onSuccess: store,
  });

  return {
    format,
    setFormat,
    depth,
    setDepth: (n: number) => setDepthRaw(Math.min(d.max_depth, Math.max(1, Math.round(n)))),
    maxDepth: d.max_depth,
    autoDepth: d.auto_depth,
    ready: view !== undefined, // false only until the very first view has loaded
    loading,
    loadError: viewQ.isError ? viewQ.error.message : null,
    nodes: view?.nodes ?? 0,
    edges: view?.edges ?? 0,
    hubs: view?.hubs ?? 0,
    text,
    setText,
    generated,
    dirty: !loading && text !== base, // differs from what is saved
    modified: !loading && text !== generated, // differs from the generated diagram
    hasSavedEdit: !!view && view.edited !== null,
    saving: save.isPending,
    saveError: save.error?.message ?? discard.error?.message ?? null,
    save: () => !loading && save.mutate({ format, depth, text }),
    reset: () => {
      if (loading) return;
      if (view && view.edited !== null) discard.mutate({ format, depth });
      else clearDraft(key);
    },
  };
}
