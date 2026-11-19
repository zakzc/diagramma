import mermaid from "mermaid";
import { useEffect, useRef } from "react";

let counter = 0;

/**
 * Renders Mermaid text into SVG. A failed render never clears the last good one; the error is
 * reported through `onResult` instead (null = rendered fine).
 */
export default function MermaidView({
  text,
  dark = false,
  onResult,
  onRendered,
}: {
  text: string;
  dark?: boolean;
  onResult?: (error: string | null) => void;
  onRendered?: (svg: SVGSVGElement) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cb = useRef({ onResult, onRendered });
  cb.current = { onResult, onRendered };

  useEffect(() => {
    let cancelled = false;
    const id = `mmd-${++counter}`;
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: dark ? "dark" : "default",
      maxTextSize: 2_000_000,
      maxEdges: 5000,
      suppressErrorRendering: true,
      // Natural size, so pan/zoom and fit-to-screen work on real dimensions.
      flowchart: { useMaxWidth: false },
      c4: { useMaxWidth: false },
    });
    mermaid
      .render(id, text)
      .then(({ svg }) => {
        if (cancelled || !ref.current) return;
        ref.current.innerHTML = svg;
        cb.current.onResult?.(null);
        const el = ref.current.querySelector("svg");
        if (el) cb.current.onRendered?.(el as SVGSVGElement);
      })
      .catch((e: unknown) => {
        document.getElementById(`d${id}`)?.remove(); // mermaid can leave its scratch node behind
        if (cancelled) return;
        cb.current.onResult?.(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [text, dark]);

  return <div ref={ref} data-testid="mermaid-output" className="p-4" />;
}
