import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { type EditFormat, getDiagram } from "../api/client";
import { useDiagramEditor } from "../api/useDiagramEditor";
import { useDebounced } from "../hooks/useDebounced";
import CodePane from "./CodePane";
import DiagramPane from "./DiagramPane";
import SplitLayout from "./SplitLayout";
import StatusBar from "./StatusBar";
import type { DiagramRecord } from "../api/client";

export const RENDER_DEBOUNCE_MS = 400;

export default function DiagramWorkspace({ diagramId }: { diagramId: string }) {
  const q = useQuery({ queryKey: ["diagram", diagramId], queryFn: () => getDiagram(diagramId) });
  if (q.isPending) return <p className="p-4 text-sm text-slate-500">Loading diagram…</p>;
  if (q.isError) return <p role="alert" className="p-4 text-sm text-red-600">{q.error.message}</p>;
  return <Editor key={diagramId} d={q.data} />;
}

function Editor({ d }: { d: DiagramRecord }) {
  const ed = useDiagramEditor(d);
  const [renderError, setRenderError] = useState<string | null>(null);
  // The diagram follows the editor after a short pause; switching tab/diagram applies at once.
  const renderText = useDebounced(ed.text, RENDER_DEBOUNCE_MS, `${d.id}:${ed.format}`);

  const btn = "rounded border px-2 py-0.5 text-xs border-slate-300 dark:border-slate-600";
  const tab = (f: EditFormat, name: string) => (
    <button
      role="tab"
      aria-selected={ed.format === f}
      className={`${btn} ${ed.format === f ? "bg-slate-200 dark:bg-slate-700" : ""}`}
      disabled={f === "flowchart" && !d.mermaid_flowchart}
      onClick={() => {
        ed.setFormat(f);
        setRenderError(null);
      }}
    >
      {name}
    </button>
  );

  // Offer the flowchart only when the generated C4 itself fails, not while the user is mid-edit.
  const offerFlowchart = renderError && ed.format === "c4" && !ed.modified && !!d.mermaid_flowchart;

  return (
    <section aria-label="Diagram workspace" className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-x-3 border-b border-slate-200 px-4 py-1.5 text-sm dark:border-slate-700">
        <b>
          {d.owner}/{d.name}
        </b>
        <span className="text-slate-500">
          {d.commit_sha.slice(0, 7)} · {d.container_count} containers · {d.component_count} components ·{" "}
          {d.model.externals.length} external
        </span>
      </div>
      {offerFlowchart && (
        <div className="flex items-center gap-2 border-b bg-red-50 px-4 py-1.5 text-sm text-red-900 dark:bg-red-950 dark:text-red-200">
          The C4 diagram could not be rendered.
          <button className={btn} onClick={() => ed.setFormat("flowchart")}>
            Show flowchart instead
          </button>
        </div>
      )}
      {d.warnings.length > 0 && (
        <ul className="border-b bg-amber-50 px-4 py-1.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {d.warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}
      <div className="min-h-0 flex-1">
        <SplitLayout
          left={{
            title: "Mermaid code",
            body: (
              <div className="flex h-full flex-col">
                <div className="min-h-0 flex-1">
                  <CodePane value={ed.text} onChange={ed.setText} />
                </div>
                <StatusBar
                  error={renderError}
                  dirty={ed.dirty}
                  canReset={ed.modified}
                  hasSavedEdit={ed.hasSavedEdit}
                  saving={ed.saving}
                  saveError={ed.saveError}
                  onSave={ed.save}
                  onReset={ed.reset}
                />
              </div>
            ),
          }}
          right={{
            title: "Diagram",
            actions: (
              <div role="tablist" aria-label="Format" className="flex gap-1">
                {tab("c4", "C4")}
                {tab("flowchart", "Flowchart")}
              </div>
            ),
            body: <DiagramPane text={renderText} fitKey={`${d.id}:${ed.format}`} onResult={setRenderError} />,
          }}
        />
      </div>
    </section>
  );
}
