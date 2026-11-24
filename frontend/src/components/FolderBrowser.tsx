import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { listDirs } from "../api/client";

export default function FolderBrowser({
  start,
  onPick,
  onClose,
}: {
  start?: string;
  onPick: (path: string) => void;
  onClose: () => void;
}) {
  const [path, setPath] = useState<string | undefined>(start || undefined);
  const [hidden, setHidden] = useState(false);
  const dirs = useQuery({
    queryKey: ["dirs", path ?? "", hidden],
    queryFn: () => listDirs(path, hidden),
    retry: false,
  });
  const listing = dirs.data;

  return (
    <div
      role="dialog"
      aria-label="Choose a folder"
      className="absolute left-0 top-full z-20 mt-1 w-[32rem] max-w-full rounded border border-slate-300 bg-white p-2 text-sm shadow-lg dark:border-slate-600 dark:bg-slate-800"
    >
      <div className="mb-1 flex items-center gap-2">
        <button
          type="button"
          className="rounded border px-2 py-0.5 disabled:opacity-40"
          disabled={!listing?.parent}
          onClick={() => listing?.parent && setPath(listing.parent)}
        >
          ↑ Up
        </button>
        <span className="min-w-0 flex-1 truncate font-mono text-xs" title={listing?.path}>
          {listing?.path ?? "…"}
        </span>
        <label className="flex shrink-0 items-center gap-1 text-xs">
          <input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} />
          Hidden
        </label>
      </div>
      {dirs.isError && (
        <p role="alert" className="text-xs text-red-600">
          {dirs.error.message}
        </p>
      )}
      <ul className="max-h-64 overflow-auto" aria-label="Folders">
        {listing?.dirs.map((d) => (
          <li key={d.path}>
            <button
              type="button"
              className="w-full truncate rounded px-2 py-0.5 text-left hover:bg-slate-100 dark:hover:bg-slate-700"
              onClick={() => setPath(d.path)}
            >
              📁 {d.name}
              {d.is_repo && <span className="ml-1 text-xs text-blue-600">repo</span>}
            </button>
          </li>
        ))}
        {listing && listing.dirs.length === 0 && <li className="px-2 text-xs text-slate-500">No sub-folders.</li>}
      </ul>
      <div className="mt-2 flex justify-end gap-2">
        <button type="button" className="rounded border px-2 py-0.5" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="rounded bg-blue-600 px-2 py-0.5 text-white disabled:opacity-50"
          disabled={!listing}
          onClick={() => listing && onPick(listing.path)}
        >
          Select this folder
        </button>
      </div>
    </div>
  );
}
