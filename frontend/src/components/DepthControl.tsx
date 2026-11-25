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
  const levels = Array.from({ length: max }, (_, i) => i + 1);
  return (
    <div role="group" aria-label="Depth" className="flex items-center gap-2">
      <span className="text-xs font-medium text-slate-500">Depth</span>
      <div className={max <= 8 ? "seg seg-sm" : ""}>
      {max <= 8 ? (
        levels.map((n) => (
          <button
            key={n}
            aria-pressed={depth === n}
            disabled={disabled}
            title={n === auto ? `Level ${n} (default: the deepest view that stays readable)` : `Level ${n}`}
            className={`seg-item ${depth === n ? "seg-on" : ""}`}
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
          className="field h-7 text-xs"
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
    </div>
  );
}
