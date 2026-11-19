import type { GenerateState } from "../api/useGenerate";

export default function ProgressPanel({ state }: { state: GenerateState }) {
  if (state.status !== "running" && state.status !== "error") return null;
  const { stages } = state;
  const lastIdx = stages.length - 1;

  return (
    <section aria-label="Progress" className="p-4 text-sm">
      <ol className="space-y-1">
        {stages.map((s, i) => {
          const active = state.status === "running" && i === lastIdx;
          return (
            <li key={`${s.stage}-${i}`} className={active ? "font-medium" : "text-slate-500"}>
              <span aria-hidden>{active ? "◐" : "●"}</span> {s.message}
            </li>
          );
        })}
      </ol>
      {state.status === "running" && stages.length === 0 && (
        <p className="text-slate-500">Starting…</p>
      )}
      {state.status === "error" && (
        <p role="alert" className="mt-3 text-red-600">
          {state.error.message} <span className="text-xs text-slate-500">({state.error.code})</span>
        </p>
      )}
    </section>
  );
}
