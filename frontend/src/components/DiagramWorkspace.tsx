import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { type EditFormat, getDiagram } from "../api/client";
import { useDiagramEditor } from "../api/useDiagramEditor";
import { useDebounced } from "../hooks/useDebounced";
import CodePane from "./CodePane";
import DepthControl from "./DepthControl";
import ImportsStrip from "./ImportsStrip";
import LayersStrip from "./LayersStrip";
import DetailsPanel from "./DetailsPanel";
import DiagramPane from "./DiagramPane";
import SplitLayout from "./SplitLayout";
import StatusBar from "./StatusBar";
import type { DiagramRecord } from "../api/client";

export const RENDER_DEBOUNCE_MS = 400;
export const LARGE_DIAGRAM_NODES = 150; // beyond this a diagram is slow to lay out and hard to read

export default function DiagramWorkspace({ diagramId }: { diagramId: string }) {
  const q = useQuery({ queryKey: ["diagram", diagramId], queryFn: () => getDiagram(diagramId) });
  if (q.isPending) return <p className="p-4 text-sm text-slate-500">Loading diagram…</p>;
  if (q.isError) return <p role="alert" className="p-4 text-sm text-red-600">{q.error.message}</p>;
  return <Editor key={diagramId} d={q.data} />;
}

function Editor({ d }: { d: DiagramRecord }) {
  const ed = useDiagramEditor(d);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [warnOpen, setWarnOpen] = useState(true);
  const [selected, setSelected] = useState<{ id: string; view: string } | null>(null);
  // The diagram follows the editor after a short pause; switching tab/diagram applies at once.
  const viewKey = `${d.id}:${ed.format}:${ed.format === "imports" ? 1 : ed.depth}`;
  // A new view (or a view finishing its load) applies at once; only typing is debounced.
  const renderText = useDebounced(ed.text, RENDER_DEBOUNCE_MS, `${viewKey}:${ed.loading}`);

  const tab = (f: EditFormat, name: string, hint?: string) => (
    <button
      role="tab"
      title={hint}
      aria-selected={ed.format === f}
      className={`seg-item ${ed.format === f ? "seg-on" : ""}`}
      disabled={ed.loading}
      onClick={() => {
        ed.setFormat(f);
        setRenderError(null);
      }}
    >
      {name}
    </button>
  );

  // Offer the flowchart only when the generated C4 itself fails, not while the user is mid-edit.
  const offerFlowchart = renderError && ed.format === "c4" && !ed.modified && !ed.loading;
  const large = ed.nodes > LARGE_DIAGRAM_NODES;

  return (
    <section aria-label="Diagram workspace" className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-slate-200 px-4 py-2 text-sm dark:border-slate-700">
        <b className="text-base">{d.source === "local" ? d.name : `${d.owner}/${d.name}`}</b>
        {d.source === "local" && (
          <span className="text-slate-500">{d.repo_url.replace(/^file:\/\//, "")}</span>
        )}
        <span className="text-slate-500">
          {d.commit_sha.slice(0, 7)} · {d.container_count} containers · {d.component_count} components ·{" "}
          {d.model.externals.length} external
        </span>
        {ed.format !== "imports" && (
          <DepthControl
            depth={ed.depth}
            max={ed.maxDepth}
            auto={ed.autoDepth}
            disabled={ed.loading}
            onChange={(n) => {
              ed.setDepth(n);
              setRenderError(null);
            }}
          />
        )}
        <span className="text-xs text-slate-500" data-testid="view-size">
          {ed.loading
            ? "loading…"
            : ed.loadError
              ? "this view is not available"
              : `showing ${ed.nodes} ${ed.format === "imports" ? "files" : "components"} · ${ed.edges} ${ed.format === "imports" ? "imports" : "relations"}`}
        </span>
        {!ed.loading && ed.hubs > 0 && (
          <span
            className="text-xs text-slate-500"
            data-testid="hub-note"
            title="Shared modules that much of the code depends on are drawn once, with a dashed border and a 'used by N' count, instead of with every incoming line. The C4 tab draws every edge."
          >
            · {ed.hubs} shared {ed.hubs === 1 ? "module" : "modules"} not wired (dashed)
          </span>
        )}
      </div>
      {ed.layers && <LayersStrip s={ed.layers} />}
      {ed.imports && <ImportsStrip s={ed.imports} />}
      {large && !ed.loading && (
        <div className="border-b bg-amber-50 px-4 py-1 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          This view has {ed.nodes} components and may be slow and hard to read. Try a lower depth.
        </div>
      )}
      {ed.loadError && (
        <div role="alert" className="border-b bg-red-50 px-4 py-1 text-xs text-red-900 dark:bg-red-950 dark:text-red-200">
          Could not load this view: {ed.loadError}
        </div>
      )}
      {offerFlowchart && (
        <div className="flex items-center gap-2 border-b bg-red-50 px-4 py-1.5 text-sm text-red-900 dark:bg-red-950 dark:text-red-200">
          The C4 diagram could not be rendered.
          <button className="btn btn-sm btn-secondary" onClick={() => ed.setFormat("flowchart")}>
            Show flowchart instead
          </button>
        </div>
      )}
      {d.warnings.length > 0 && warnOpen && (
        <div className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-1 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <ul className="min-w-0 flex-1 py-1">
            {d.warnings.map((w) => (
              <li key={w}>⚠ {w}</li>
            ))}
          </ul>
          <button aria-label="Dismiss warnings" title="Dismiss" className="btn btn-ghost btn-sm" onClick={() => setWarnOpen(false)}>
            ✕
          </button>
        </div>
      )}
      <div className="min-h-0 flex-1">
        {!ed.ready ? (
          <p className="p-4 text-sm text-slate-500">{ed.loadError ? "" : "Loading diagram…"}</p>
        ) : (
          <SplitLayout
            left={{
              title: "Mermaid code",
              body: (
                <div className="flex h-full flex-col">
                  <div className="min-h-0 flex-1">
                    <CodePane value={ed.text} onChange={ed.setText} readOnly={ed.stale} />
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
                <div role="tablist" aria-label="Format" className="seg seg-sm">
                  {tab("flowchart", "Flowchart")}
                  {tab("c4", "C4")}
                  {tab(
                    "layers",
                    "Dependencies",
                    "Layered dependency graph from import statements: importers above, what they import below",
                  )}
                  {tab(
                    "imports",
                    "Imports",
                    "React apps: every file with what it imports, coloured by kind (component, hook, API, database, ...)",
                  )}
                </div>
              ),
              body: (
                <DiagramPane
                  text={renderText}
                  fitKey={viewKey}
                  onResult={setRenderError}
                  onNodeClick={(id) => setSelected({ id, view: viewKey })}
                  overlay={
                    selected?.view === viewKey && (
                      <DetailsPanel
                        diagramId={d.id}
                        nodeId={selected.id}
                        depth={ed.format === "imports" ? 1 : ed.depth}
                        onSelect={(id) => setSelected({ id, view: viewKey })}
                        onClose={() => setSelected(null)}
                      />
                    )
                  }
                />
              ),
            }}
          />
        )}
      </div>
    </section>
  );
}
