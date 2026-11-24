import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { deleteDiagram, listDiagrams } from "../api/client";

export default function HistoryList({
  selectedId,
  onSelect,
  onDeleted,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDeleted: (id: string) => void;
}) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["diagrams"], queryFn: listDiagrams });
  const [confirming, setConfirming] = useState<string | null>(null);
  const remove = useMutation({
    mutationFn: deleteDiagram,
    onSuccess: (_, id) => {
      setConfirming(null);
      onDeleted(id);
      qc.invalidateQueries({ queryKey: ["diagrams"] });
    },
  });

  if (list.isPending) return <p className="p-3 text-sm text-slate-500">Loading history…</p>;
  if (list.isError) return <p role="alert" className="p-3 text-sm text-red-600">{list.error.message}</p>;
  if (list.data.length === 0) return <p className="p-3 text-sm text-slate-500">No diagrams yet.</p>;

  return (
    <ul aria-label="History" className="divide-y divide-slate-200 dark:divide-slate-700">
      {list.data.map((d) => (
        <li key={d.id} className={selectedId === d.id ? "bg-slate-100 dark:bg-slate-800" : ""}>
          <div className="flex items-start gap-1 p-2">
            <button
              className="min-w-0 flex-1 text-left"
              aria-current={selectedId === d.id}
              title={d.source === "local" ? d.repo_url.replace(/^file:\/\//, "") : undefined}
              onClick={() => onSelect(d.id)}
            >
              <div className="truncate text-sm font-medium">
                {d.source === "local" ? d.name : `${d.owner}/${d.name}`}
              </div>
              <div className="truncate text-xs text-slate-500">
                {d.ref ? `${d.ref} · ` : ""}
                {d.commit_sha.slice(0, 7)} · {new Date(d.created_at).toLocaleDateString()}
              </div>
              <div className="text-xs text-slate-500">
                {d.container_count} containers · {d.component_count} components
              </div>
            </button>
            {confirming === d.id ? (
              <span className="flex shrink-0 gap-1 text-xs">
                <button
                  className="rounded bg-red-600 px-1.5 py-0.5 text-white"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(d.id)}
                >
                  Delete
                </button>
                <button className="rounded border px-1.5 py-0.5" onClick={() => setConfirming(null)}>
                  Cancel
                </button>
              </span>
            ) : (
              <button
                aria-label={`Delete ${d.source === "local" ? d.name : `${d.owner}/${d.name}`}`}
                className="shrink-0 rounded px-1.5 text-slate-400 hover:text-red-600"
                onClick={() => setConfirming(d.id)}
              >
                ✕
              </button>
            )}
          </div>
        </li>
      ))}
      {remove.isError && (
        <li role="alert" className="p-2 text-xs text-red-600">
          {remove.error.message}
        </li>
      )}
    </ul>
  );
}
