import { useQuery } from "@tanstack/react-query";
import { type NodeDetails, getNode } from "../api/client";

const row = "flex gap-2 text-xs";

function Links({ title, links, onSelect }: { title: string; links: NodeDetails["uses"]; onSelect: (id: string) => void }) {
  if (links.length === 0) return null;
  return (
    <section aria-label={title}>
      <h3 className="mt-3 text-xs font-semibold uppercase text-slate-500">
        {title} ({links.length})
      </h3>
      <ul className="mt-1 space-y-0.5">
        {links.map((l) => (
          <li key={l.id}>
            <button
              className="w-full truncate text-left text-xs text-blue-700 hover:underline dark:text-blue-400"
              title={[l.label, ...l.evidence].join(" · ")}
              onClick={() => onSelect(l.id)}
            >
              {l.name}
              {l.strength > 1 && <span className="text-slate-500"> ×{l.strength}</span>}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Everything the model knows about the clicked box (SPEC §9.5). */
export default function DetailsPanel({
  diagramId,
  nodeId,
  depth,
  onSelect,
  onClose,
}: {
  diagramId: string;
  nodeId: string;
  depth: number;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const q = useQuery({
    queryKey: ["node", diagramId, nodeId, depth],
    queryFn: () => getNode(diagramId, nodeId, depth),
    retry: false,
  });
  const n = q.data;
  const field = (label: string, value: string | number | null | undefined) =>
    value ? (
      <div className={row}>
        <span className="w-20 shrink-0 text-slate-500">{label}</span>
        <span className="min-w-0 break-words">{value}</span>
      </div>
    ) : null;

  return (
    <aside
      aria-label="Details"
      className="absolute right-2 top-2 z-10 max-h-[calc(100%-1rem)] w-80 overflow-auto rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900 shadow-xl"
    >
      <div className="flex items-start gap-2">
        <h2 className="min-w-0 flex-1 break-words font-semibold">{n?.name ?? (q.isPending ? "Loading…" : nodeId)}</h2>
        <button aria-label="Close details" title="Close" className="btn btn-ghost btn-sm shrink-0" onClick={onClose}>
          ✕
        </button>
      </div>
      {q.isError && (
        <p role="alert" className="mt-2 text-xs text-slate-500">
          {q.error.message}
        </p>
      )}
      {n && (
        <div className="mt-2 space-y-0.5">
          {field("Kind", [n.kind, n.role].filter(Boolean).join(" · "))}
          {field("Technology", n.technology)}
          {field("Container", n.container)}
          {field("In", n.trail.join(" › "))}
          {field("Description", n.description)}
          {field("Paths", n.paths.join(", "))}
          {field("Lines", n.weight)}
          {field("Files", n.file_count)}
          {n.is_hub && <p className="pt-1 text-xs text-amber-700">Shared module: its incoming edges are not drawn in the flowchart.</p>}
          {n.evidence.length > 0 && (
            <div className="pt-1 text-xs">
              <span className="text-slate-500">Evidence</span>
              <ul className="list-disc pl-4">
                {n.evidence.map((e) => (
                  <li key={e} className="break-words">
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {n.children.length > 0 && field("Contains", n.children.join(", "))}
          <Links title="Uses" links={n.uses} onSelect={onSelect} />
          <Links title="Used by" links={n.used_by} onSelect={onSelect} />
        </div>
      )}
    </aside>
  );
}
