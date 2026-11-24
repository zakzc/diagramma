import { type ReactNode, useRef, useState } from "react";
import { TransformComponent, TransformWrapper, type ReactZoomPanPinchRef } from "react-zoom-pan-pinch";
import MermaidView from "./MermaidView";

/** The Mermaid id of the box (flowchart node or subgraph) under a click, if any. */
function nodeIdAt(target: EventTarget | null): string | null {
  const g = (target as Element | null)?.closest?.("g.node, g.cluster");
  if (!g?.id) return null;
  const raw = g.id.replace(/^mmd-\d+-/, ""); // Mermaid prefixes ids with the render id
  return /^flowchart-(.+)-\d+$/.exec(raw)?.[1] ?? raw; // C4 ids are the plain alias
}

/** Pan/zoom rendering of `text`, with fit-to-screen and Copy. Fits once per `fitKey`. */
export default function DiagramPane({
  text,
  fitKey,
  onResult,
  onNodeClick,
  overlay,
}: {
  text: string;
  fitKey: string;
  onResult: (error: string | null) => void;
  onNodeClick?: (id: string) => void;
  overlay?: ReactNode;
}) {
  const down = useRef<[number, number] | null>(null);
  const zoom = useRef<ReactZoomPanPinchRef | null>(null);
  const fitted = useRef<string | null>(null);
  const [copied, setCopied] = useState(false);

  const fit = () => zoom.current?.fitToView({ animationTime: 0 });
  const btn = "rounded border px-2 py-0.5 text-xs border-slate-300 dark:border-slate-600";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-slate-200 px-3 py-1 dark:border-slate-700">
        <button className={btn} aria-label="Zoom in" onClick={() => zoom.current?.zoomIn()}>
          +
        </button>
        <button className={btn} aria-label="Zoom out" onClick={() => zoom.current?.zoomOut()}>
          −
        </button>
        <button className={btn} onClick={fit}>
          Fit
        </button>
        <span className="flex-1" />
        <button
          className={btn}
          title="Copy the Mermaid text of this diagram"
          onClick={() =>
            navigator.clipboard
              ?.writeText(text)
              .then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              })
              .catch(() => {})
          }
        >
          {copied ? "Copied" : "Copy .mmd"}
        </button>
      </div>
      {/* Always a light canvas: Mermaid's dark C4 theme leaves container and relation labels
          nearly unreadable, so the diagram keeps the default theme in both UI themes. */}
      <div
        className="relative min-h-0 flex-1 bg-white"
        onPointerDown={(e) => (down.current = [e.clientX, e.clientY])}
        onClick={(e) => {
          // A drag (pan) also ends in a click: only a click that did not move selects a box.
          const [x, y] = down.current ?? [e.clientX, e.clientY];
          if (Math.hypot(e.clientX - x, e.clientY - y) > 4) return;
          const id = nodeIdAt(e.target);
          if (id) onNodeClick?.(id);
        }}
      >
        <TransformWrapper
          ref={zoom}
          minScale={0.05}
          maxScale={8}
          limitToBounds={false}
          doubleClick={{ disabled: true }}
        >
          <TransformComponent wrapperStyle={{ width: "100%", height: "100%" }}>
            <MermaidView
              text={text}
              onResult={onResult}
              onRendered={() => {
                if (fitted.current === fitKey) return; // keep the user's pan/zoom while typing
                fitted.current = fitKey;
                setTimeout(fit, 30);
              }}
            />
          </TransformComponent>
        </TransformWrapper>
        {overlay}
      </div>
    </div>
  );
}
