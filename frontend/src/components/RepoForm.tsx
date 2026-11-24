import { useState } from "react";
import { type RepoInput, validatePathInput, validateRepoInput } from "../api/repoInput";
import FolderBrowser from "./FolderBrowser";

export default function RepoForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (input: RepoInput) => void;
}) {
  const [mode, setMode] = useState<"github" | "local">("github");
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [path, setPath] = useState("");
  const [browsing, setBrowsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const field =
    "rounded border px-2 py-1 text-sm bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600";
  const local = mode === "local";

  return (
    <form
      className="relative flex flex-1 items-start gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const v = local ? validatePathInput(path) : validateRepoInput(url, ref);
        if (!v.ok) return setError(v.error);
        setError(null);
        onSubmit(v.value);
      }}
    >
      <fieldset className="flex shrink-0 gap-2 py-1 text-sm">
        <legend className="sr-only">Source</legend>
        {(["github", "local"] as const).map((m) => (
          <label key={m} className="flex items-center gap-1">
            <input
              type="radio"
              name="source"
              checked={mode === m}
              onChange={() => {
                setMode(m);
                setError(null);
                setBrowsing(false);
              }}
            />
            {m === "github" ? "GitHub URL" : "Local folder"}
          </label>
        ))}
      </fieldset>
      <div className="flex-1">
        {local ? (
          <div className="flex gap-2">
            <input
              aria-label="Folder path"
              className={`${field} w-full`}
              placeholder="/absolute/path/to/repo"
              value={path}
              onChange={(e) => setPath(e.target.value)}
            />
            <button type="button" className="shrink-0 rounded border px-2 py-1 text-sm" onClick={() => setBrowsing(!browsing)}>
              Browse…
            </button>
          </div>
        ) : (
          <input
            aria-label="GitHub repo URL"
            className={`${field} w-full`}
            placeholder="https://github.com/owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        )}
        {error && (
          <p role="alert" className="mt-1 text-xs text-red-600">
            {error}
          </p>
        )}
      </div>
      {browsing && (
        <FolderBrowser
          start={path.trim().startsWith("/") ? path.trim() : undefined}
          onPick={(p) => {
            setPath(p);
            setError(null);
            setBrowsing(false);
          }}
          onClose={() => setBrowsing(false)}
        />
      )}
      {!local && (
        <input
          aria-label="Branch, tag or commit"
          className={`${field} w-40`}
          placeholder="ref (optional)"
          value={ref}
          onChange={(e) => setRef(e.target.value)}
        />
      )}
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
      >
        {busy ? "Working…" : "Generate"}
      </button>
    </form>
  );
}
