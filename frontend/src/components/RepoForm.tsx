import { useState } from "react";
import { type RepoInput, validateRepoInput } from "../api/repoInput";

export default function RepoForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (input: RepoInput) => void;
}) {
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [error, setError] = useState<string | null>(null);

  const field =
    "rounded border px-2 py-1 text-sm bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600";

  return (
    <form
      className="flex flex-1 items-start gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const v = validateRepoInput(url, ref);
        if (!v.ok) return setError(v.error);
        setError(null);
        onSubmit(v.value);
      }}
    >
      <div className="flex-1">
        <input
          aria-label="GitHub repo URL"
          className={`${field} w-full`}
          placeholder="https://github.com/owner/repo"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        {error && (
          <p role="alert" className="mt-1 text-xs text-red-600">
            {error}
          </p>
        )}
      </div>
      <input
        aria-label="Branch, tag or commit"
        className={`${field} w-40`}
        placeholder="ref (optional)"
        value={ref}
        onChange={(e) => setRef(e.target.value)}
      />
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
