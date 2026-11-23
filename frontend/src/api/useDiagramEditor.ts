import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  type DiagramRecord,
  type DiagramView,
  type EditFormat,
  discardEdit,
  getView,
  saveEdit,
} from "./client";

/**
 * Editor state for one diagram. A "view" is a format at a depth, and each view has its own text:
 * unsaved draft > saved edit > generated. A draft equal to what is saved is not a draft.
 * Switching view keeps the previous one on screen (read-only) until the new text has loaded.
 */
export function useDiagramEditor(d: DiagramRecord) {
  const qc = useQueryClient();
  const [format, setFormat] = useState<EditFormat>("flowchart");
  const [chosenDepth, setDepthRaw] = useState(d.auto_depth);
  // The Imports view draws files and has no depth: it always lives at depth 1, so its edit and
  // draft do not depend on the depth chosen for the other views.
  const depth = format === "imports" ? 1 : chosenDepth;
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const key = `${format}:${depth}`;

  const viewQ = useQuery({
    queryKey: ["view", d.id, format, depth],
    queryFn: () => getView(d.id, format, depth),
    placeholderData: keepPreviousData,
    retry: false, // the backend is local: a failure (e.g. "regenerate this diagram") will not heal
  });
  // The last view that loaded stays on screen (read-only) while the next one loads or fails,
  // so a failed view never traps the user without an editor or tabs.
  const lastGood = useRef<DiagramView | undefined>(undefined);
  if (viewQ.data && !viewQ.isPlaceholderData) lastGood.current = viewQ.data;
  const view = viewQ.data ?? lastGood.current;
  const loading = viewQ.isFetching && (viewQ.isPending || viewQ.isPlaceholderData);
  const stale = loading || viewQ.isError; // what is shown is not this view's own text
  const generated = view?.generated ?? "";
  const base = view ? (view.edited ?? view.generated) : "";
  const text = drafts[key] ?? base;

  const setText = (next: string) => {
    if (stale) return;
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
    depth: chosenDepth,
    setDepth: (n: number) => setDepthRaw(Math.min(d.max_depth, Math.max(1, Math.round(n)))),
    maxDepth: d.max_depth,
    autoDepth: d.auto_depth,
    ready: view !== undefined, // false only until the very first view has loaded
    loading,
    stale,
    loadError: viewQ.isError ? viewQ.error.message : null,
    nodes: view?.nodes ?? 0,
    edges: view?.edges ?? 0,
    hubs: view?.hubs ?? 0,
    layers: stale ? null : (view?.layers ?? null), // only for the Dependency graph
    imports: stale ? null : (view?.imports ?? null), // only for the Imports view
    text,
    setText,
    generated,
    dirty: !stale && text !== base, // differs from what is saved
    modified: !stale && text !== generated, // differs from the generated diagram
    hasSavedEdit: !!view && view.edited !== null,
    saving: save.isPending,
    saveError: save.error?.message ?? discard.error?.message ?? null,
    save: () => !stale && save.mutate({ format, depth, text }),
    reset: () => {
      if (stale) return;
      if (view && view.edited !== null) discard.mutate({ format, depth });
      else clearDraft(key);
    },
  };
}
