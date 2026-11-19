import type { LayersSummary } from "../api/client";

/** What the Dependency graph shows, and (so nothing is silently lost) what it left out. */
export default function LayersStrip({ s }: { s: LayersSummary }) {
  const omitted = [
    s.edges_transitive_omitted > 0 && `${s.edges_transitive_omitted} implied by another path`,
    s.edges_long_omitted > 0 && `${s.edges_long_omitted} spanning more than ${s.max_span} layers`,
  ].filter(Boolean);
  return (
    <div
      data-testid="layers-strip"
      className="border-b border-slate-200 px-4 py-1 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-300"
    >
      <span>
        <b>{s.layer_count}</b> {s.layer_count === 1 ? "layer" : "layers"} · longest chain{" "}
        <b>{s.longest_chain}</b> · {s.nodes} components
      </span>
      {" · "}
      {s.upward_edges > 0 ? (
        <span className="text-red-700 dark:text-red-400">
          <b>{s.upward_edges}</b> upward {s.upward_edges === 1 ? "dependency" : "dependencies"} (not
          drawn)
        </span>
      ) : (
        <span>no import cycles</span>
      )}
      {omitted.length > 0 && <span> · left out: {omitted.join(", ")}</span>}
      {s.isolated > 0 && <span> · {s.isolated} with no import link not drawn</span>}
      {s.top_upward.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer">
            Strongest upward dependencies ({s.top_upward.length})
          </summary>
          <p className="mt-1 text-slate-500">
            An import that goes against the layer order, so these components depend on each other in a
            cycle. Their boxes are dashed with a ↑ count.
          </p>
          <ul className="mt-1 list-disc pl-5">
            {s.top_upward.map((e) => (
              <li key={`${e.source}>${e.target}`}>
                {e.source} → {e.target} <span className="text-slate-500">×{e.strength}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
