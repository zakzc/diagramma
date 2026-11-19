/** Picks how many folder levels are expanded (1 = top-level components only). */
export default function DepthControl({
  depth,
  max,
  auto,
  disabled,
  onChange,
}: {
  depth: number;
  max: number;
  auto: number;
  disabled?: boolean;
  onChange: (depth: number) => void;
}) {
  if (max <= 1) return null; // a flat model has nothing to expand
  const btn = "rounded border px-1.5 py-0.5 text-xs border-slate-300 dark:border-slate-600";
  const levels = Array.from({ length: max }, (_, i) => i + 1);
  return (
    <div role="group" aria-label="Depth" className="flex items-center gap-1">
      <span className="text-xs text-slate-500">Depth</span>
      {max <= 8 ? (
        levels.map((n) => (
          <button
            key={n}
            aria-pressed={depth === n}
            disabled={disabled}
            title={n === auto ? `Level ${n} (default: the deepest view that stays readable)` : `Level ${n}`}
            className={`${btn} ${depth === n ? "bg-slate-200 font-semibold dark:bg-slate-700" : ""}`}
            onClick={() => onChange(n)}
          >
            {n}
            {n === auto && <span aria-label="default">·</span>}
          </button>
        ))
      ) : (
        <select
          aria-label="Depth level"
          value={depth}
          disabled={disabled}
          className={btn}
          onChange={(e) => onChange(Number(e.target.value))}
        >
          {levels.map((n) => (
            <option key={n} value={n}>
              {n}
              {n === auto ? " (default)" : ""}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
