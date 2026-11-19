import { useRef, useState } from "react";
import { TransformComponent, TransformWrapper, type ReactZoomPanPinchRef } from "react-zoom-pan-pinch";
import MermaidView from "./MermaidView";

/** Pan/zoom rendering of `text`, with fit-to-screen and Copy. Fits once per `fitKey`. */
export default function DiagramPane({
  text,
  fitKey,
  onResult,
}: {
  text: string;
  fitKey: string;
  onResult: (error: string | null) => void;
}) {
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
      <div className="min-h-0 flex-1 bg-white">
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
      </div>
    </div>
  );
}
