import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getHealth } from "./api/client";
import { useGenerate } from "./api/useGenerate";
import DiagramWorkspace from "./components/DiagramWorkspace";
import HistoryList from "./components/HistoryList";
import ProgressPanel from "./components/ProgressPanel";
import RepoForm from "./components/RepoForm";

const FOLD_KEY = "diagramma.history.collapsed";

function readFolded(): boolean {
  try {
    const stored = localStorage.getItem(FOLD_KEY);
    if (stored !== null) return stored === "1";
  } catch {
    /* storage unavailable: use the default below */
  }
  // No saved choice: start folded on narrow screens so the diagram gets the width.
  return typeof window.matchMedia === "function" && window.matchMedia("(max-width: 899px)").matches;
}

export default function App() {
  const qc = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth });
  const { state, start, reset } = useGenerate();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [folded, setFolded] = useState(readFolded);

  useEffect(() => {
    if (state.status === "done") {
      setSelectedId(state.diagramId);
      qc.invalidateQueries({ queryKey: ["diagrams"] });
    }
  }, [state, qc]);

  const toggleFold = () =>
    setFolded((f) => {
      try {
        localStorage.setItem(FOLD_KEY, f ? "0" : "1");
      } catch {
        /* storage unavailable: the fold just won't persist */
      }
      return !f;
    });

  const busy = state.status === "running";
  return (
    <div className="h-full flex flex-col bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100">
      <header className="flex items-start gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 dark:border-slate-700 dark:bg-slate-800/60">
        <button
          aria-label={folded ? "Show history" : "Hide history"}
          title={folded ? "Show history" : "Hide history"}
          className="btn btn-ghost"
          onClick={toggleFold}
        >
          ☰
        </button>
        <h1 className="py-1 text-base font-semibold">Diagramma</h1>
        <RepoForm busy={busy} onSubmit={start} />
        <span className="shrink-0 py-1.5 text-xs text-slate-500">
          {health.isPending && "backend: …"}
          {health.isError && "backend: unreachable"}
          {health.data && `backend: ${health.data.status} v${health.data.version}`}
        </span>
      </header>
      <div className="flex min-h-0 flex-1">
        <aside
          aria-label="History sidebar"
          className={`shrink-0 overflow-y-auto border-r border-slate-200 dark:border-slate-700 ${
            folded ? "w-0 border-r-0" : "w-72"
          }`}
          hidden={folded}
        >
          <h2 className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">History</h2>
          <HistoryList
            selectedId={selectedId}
            onSelect={(id) => {
              reset();
              setSelectedId(id);
            }}
            onDeleted={(id) => setSelectedId((cur) => (cur === id ? null : cur))}
          />
        </aside>
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <ProgressPanel state={state} />
          {!busy && state.status !== "error" && selectedId && (
            <div className="min-h-0 flex-1">
              <DiagramWorkspace diagramId={selectedId} />
            </div>
          )}
          {!busy && state.status !== "error" && !selectedId && (
            <p className="p-6 text-sm text-slate-500">
              Paste a GitHub repo URL above and press Generate, or open a diagram from the history.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
