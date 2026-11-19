import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { type DiagramRecord, type EditFormat, discardEdit, saveEdit } from "./client";

type Drafts = Record<EditFormat, string | null>;

/**
 * Editor state for one diagram. Each format keeps its own text:
 * unsaved draft > saved edit > generated. A draft equal to what is saved is not a draft.
 */
export function useDiagramEditor(d: DiagramRecord) {
  const qc = useQueryClient();
  const [format, setFormat] = useState<EditFormat>("c4");
  const [drafts, setDrafts] = useState<Drafts>({ c4: null, flowchart: null });

  const generated: Record<EditFormat, string> = { c4: d.mermaid_c4, flowchart: d.mermaid_flowchart ?? "" };
  const saved: Record<EditFormat, string | null> = {
    c4: d.edited_c4 ?? null,
    flowchart: d.edited_flowchart ?? null,
  };
  const base = saved[format] ?? generated[format];
  const text = drafts[format] ?? base;

  const setText = (next: string) => setDrafts((cur) => ({ ...cur, [format]: next === base ? null : next }));
  const clearDraft = (f: EditFormat) => setDrafts((cur) => ({ ...cur, [f]: null }));
  const store = (rec: DiagramRecord) => qc.setQueryData(["diagram", d.id], rec);

  const save = useMutation({
    mutationFn: (v: { format: EditFormat; text: string }) => saveEdit(d.id, v.format, v.text),
    onSuccess: (rec, v) => {
      store(rec);
      clearDraft(v.format);
      qc.invalidateQueries({ queryKey: ["diagrams"] });
    },
  });
  const discard = useMutation({
    mutationFn: (f: EditFormat) => discardEdit(d.id, f),
    onSuccess: (rec, f) => {
      store(rec);
      clearDraft(f);
    },
  });

  return {
    format,
    setFormat,
    text,
    setText,
    generated: generated[format],
    dirty: text !== base, // differs from what is saved
    modified: text !== generated[format], // differs from the generated diagram
    hasSavedEdit: saved[format] !== null,
    saving: save.isPending,
    saveError: save.error?.message ?? discard.error?.message ?? null,
    save: () => save.mutate({ format, text }),
    reset: () => (saved[format] !== null ? discard.mutate(format) : clearDraft(format)),
  };
}
