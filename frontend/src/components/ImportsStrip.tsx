import type { ImportsSummary } from "../api/client";

/** The colour key of the Imports view, plus what it left out so nothing is silently lost. */
export default function ImportsStrip({ s }: { s: ImportsSummary }) {
  const notes = [
    s.hubs > 0 &&
      `${s.hubs} shared ${s.hubs === 1 ? "file" : "files"} drawn once (dashed, "used by N") instead of with ${s.hub_edges_omitted} incoming edges`,
    s.isolated > 0 && `${s.isolated} files with no import link not drawn`,
    s.packages_not_drawn > 0 && `${s.packages_not_drawn} other npm packages not drawn`,
  ].filter(Boolean);
  return (
    <div
      data-testid="imports-strip"
      className="border-b border-slate-200 px-4 py-1 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-300"
    >
      <ul aria-label="Legend" className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {s.legend.map((l) => (
          <li key={l.kind} className="flex items-center gap-1">
            <span
              aria-hidden
              className="inline-block h-3 w-3 rounded-sm border border-slate-500"
              style={{ backgroundColor: l.color }}
            />
            {l.label} <span className="text-slate-500">{l.count}</span>
          </li>
        ))}
      </ul>
      {notes.length > 0 && <p className="mt-0.5 text-slate-500">Left out: {notes.join(" · ")}</p>}
    </div>
  );
}
