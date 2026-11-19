import { type KeyboardEvent, type PointerEvent, type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { useMediaQuery } from "../hooks/useMediaQuery";

/** Which panes are open: both, the code only (diagram folded) or the diagram only. */
export type Fold = "split" | "code" | "diagram";
export type PaneSpec = { title: string; actions?: ReactNode; body: ReactNode };

export const STORAGE_KEY = "diagramma.split";
export const DEFAULT_RATIO = 1 / 3;
const MIN = 0.15;
const MAX = 0.85;
const KEY_STEP = 0.02;
const STACK_QUERY = "(max-width: 899px)"; // below this the panes stack vertically
const RAIL = "2.25rem";

const clamp = (r: number) => Math.min(MAX, Math.max(MIN, r));

function load(): { fold: Fold; ratio: number } {
  try {
    const v = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    const fold: Fold = v?.fold === "code" || v?.fold === "diagram" ? v.fold : "split";
    const ratio = typeof v?.ratio === "number" && Number.isFinite(v.ratio) ? clamp(v.ratio) : DEFAULT_RATIO;
    return { fold, ratio };
  } catch {
    return { fold: "split", ratio: DEFAULT_RATIO };
  }
}

function save(v: { fold: Fold; ratio: number }) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(v));
  } catch {
    /* storage unavailable: the layout just won't persist */
  }
}

export default function SplitLayout({ left, right }: { left: PaneSpec; right: PaneSpec }) {
  const stacked = useMediaQuery(STACK_QUERY);
  const [{ fold, ratio }, setState] = useState(load);
  const box = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const update = useCallback((next: Partial<{ fold: Fold; ratio: number }>) => {
    setState((s) => {
      const merged = { ...s, ...next };
      save(merged);
      return merged;
    });
  }, []);

  // Keyboard shortcuts: Alt+1 folds/unfolds the code pane, Alt+2 the diagram pane.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (!e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.code === "Digit1") {
        if (fold === "split") update({ fold: "diagram" });
        else if (fold === "diagram") update({ fold: "split" });
      } else if (e.code === "Digit2") {
        if (fold === "split") update({ fold: "code" });
        else if (fold === "code") update({ fold: "split" });
      } else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fold, update]);

  const ratioFromPointer = (e: PointerEvent) => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return null;
    const size = stacked ? r.height : r.width;
    if (size <= 0) return null;
    return clamp((stacked ? e.clientY - r.top : e.clientX - r.left) / size);
  };

  const onDown = (e: PointerEvent) => {
    dragging.current = true;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  };
  const onMove = (e: PointerEvent) => {
    if (!dragging.current) return;
    const r = ratioFromPointer(e);
    if (r !== null) setState((s) => ({ ...s, ratio: r }));
  };
  const onUp = (e: PointerEvent) => {
    if (!dragging.current) return;
    dragging.current = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    setState((s) => {
      save(s);
      return s;
    });
  };
  const onDividerKey = (e: KeyboardEvent) => {
    const back = stacked ? "ArrowUp" : "ArrowLeft";
    const fwd = stacked ? "ArrowDown" : "ArrowRight";
    if (e.key === back) update({ ratio: clamp(ratio - KEY_STEP) });
    else if (e.key === fwd) update({ ratio: clamp(ratio + KEY_STEP) });
    else if (e.key === "Home" || e.key === "Enter") update({ ratio: DEFAULT_RATIO });
    else return;
    e.preventDefault();
  };

  const template =
    fold === "split"
      ? `minmax(0,${ratio}fr) 6px minmax(0,${1 - ratio}fr)`
      : fold === "code"
        ? `minmax(0,1fr) ${RAIL}`
        : `${RAIL} minmax(0,1fr)`;

  const glyph = {
    foldLeft: stacked ? "▴" : "‹",
    foldRight: stacked ? "▾" : "›",
    unfoldLeft: stacked ? "▾" : "›",
    unfoldRight: stacked ? "▴" : "‹",
  };

  const pane = (side: "left" | "right", spec: PaneSpec) => {
    const folded = (side === "left" && fold === "diagram") || (side === "right" && fold === "code");
    const lastOpen = fold !== "split" && !folded; // the only open pane cannot be folded
    const onlyOther = side === "left" ? "diagram" : "code";
    return (
      <section aria-label={spec.title} className="flex min-h-0 min-w-0 flex-col bg-white dark:bg-slate-900">
        {folded ? (
          <div className={`flex ${stacked ? "flex-row items-center" : "h-full flex-col items-center"} gap-2 py-1 px-1 bg-slate-50 dark:bg-slate-800`}>
            <button
              aria-label={`Unfold ${spec.title}`}
              title={`Unfold ${spec.title}`}
              className="rounded px-1.5 text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700"
              onClick={() => update({ fold: "split" })}
            >
              {side === "left" ? glyph.unfoldLeft : glyph.unfoldRight}
            </button>
            <span
              className="text-xs text-slate-500"
              style={stacked ? undefined : { writingMode: "vertical-rl" }}
            >
              {spec.title}
            </span>
          </div>
        ) : (
          <header className="flex items-center gap-2 border-b border-slate-200 px-3 py-1.5 text-sm dark:border-slate-700">
            <h3 className="font-medium">{spec.title}</h3>
            <span className="flex-1" />
            {spec.actions}
            <button
              aria-label={`Fold ${spec.title}`}
              title={lastOpen ? "At least one pane must stay open" : `Fold ${spec.title}`}
              disabled={lastOpen}
              className="rounded px-1.5 text-slate-600 hover:bg-slate-200 disabled:opacity-30 dark:text-slate-300 dark:hover:bg-slate-700"
              onClick={() => update({ fold: onlyOther })}
            >
              {side === "left" ? glyph.foldLeft : glyph.foldRight}
            </button>
          </header>
        )}
        {/* Stays mounted while folded so the editor and the render keep their state. */}
        <div hidden={folded} className="min-h-0 flex-1 overflow-hidden">
          {spec.body}
        </div>
      </section>
    );
  };

  return (
    <div
      ref={box}
      data-testid="split"
      data-fold={fold}
      data-orientation={stacked ? "stacked" : "side-by-side"}
      className="grid h-full min-h-0 w-full"
      style={stacked ? { gridTemplateRows: template } : { gridTemplateColumns: template }}
    >
      {pane("left", left)}
      {fold === "split" && (
        <div
          role="separator"
          tabIndex={0}
          aria-label="Resize panes"
          aria-orientation={stacked ? "horizontal" : "vertical"}
          aria-valuemin={Math.round(MIN * 100)}
          aria-valuemax={Math.round(MAX * 100)}
          aria-valuenow={Math.round(ratio * 100)}
          title="Drag to resize, double-click to reset"
          className={`bg-slate-200 hover:bg-blue-400 focus:bg-blue-400 focus:outline-none dark:bg-slate-700 ${
            stacked ? "cursor-row-resize" : "cursor-col-resize"
          }`}
          style={{ touchAction: "none" }}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
          onDoubleClick={() => update({ ratio: DEFAULT_RATIO })}
          onKeyDown={onDividerKey}
        />
      )}
      {pane("right", right)}
    </div>
  );
}
