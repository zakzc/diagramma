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
      <fieldset className="seg">
        <legend className="sr-only">Source</legend>
        {(["github", "local"] as const).map((m) => (
          <label key={m} className="seg-item has-[:checked]:bg-blue-600 has-[:checked]:font-medium has-[:checked]:text-white has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-inset has-[:focus-visible]:ring-blue-500">
            <input
              className="sr-only"
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
              className="field w-full"
              placeholder="/absolute/path/to/repo"
              value={path}
              onChange={(e) => setPath(e.target.value)}
            />
            <button type="button" className="btn btn-secondary" onClick={() => setBrowsing(!browsing)}>
              Browse…
            </button>
          </div>
        ) : (
          <input
            aria-label="GitHub repo URL"
            className="field w-full"
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
          className="field w-44"
          placeholder="Branch or tag (optional)"
          value={ref}
          onChange={(e) => setRef(e.target.value)}
        />
      )}
      <button
        type="submit"
        disabled={busy}
        className="btn btn-primary"
      >
        {busy ? "Working…" : "Generate"}
      </button>
    </form>
  );
}
