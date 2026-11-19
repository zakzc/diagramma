import { useState } from "react";

/** The useful part of a Mermaid parse error, plus the line number when it names one. */
export function summarizeError(message: string): { line: number | null; text: string } {
  const lines = message.split("\n").map((l) => l.trim()).filter(Boolean);
  const line = /line (\d+)/i.exec(message)?.[1];
  // Multi-line parse errors end with the "Expecting …, got …" line; the first line only repeats the number.
  const picked = lines.length > 1 ? lines[lines.length - 1] : (lines[0] ?? message);
  const text = picked.replace(/^Parse error on line \d+:\s*/i, "") || picked;
  return { line: line ? Number(line) : null, text };
}

export default function StatusBar({
  error,
  dirty,
  canReset,
  hasSavedEdit,
  saving,
  saveError,
  onSave,
  onReset,
}: {
  error: string | null;
  dirty: boolean;
  canReset: boolean;
  hasSavedEdit: boolean;
  saving: boolean;
  saveError: string | null;
  onSave: () => void;
  onReset: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const btn = "rounded border px-2 py-0.5 text-xs border-slate-300 disabled:opacity-40 dark:border-slate-600";
  const summary = error ? summarizeError(error) : null;

  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 px-3 py-1.5 text-xs dark:border-slate-700">
      <span role="status" aria-live="polite" className="line-clamp-2 min-w-0 flex-1 break-words" title={error ?? undefined}>
        {summary ? (
          <span className="text-red-600">
            ✕ {summary.line !== null && <b>Line {summary.line}: </b>}
            {summary.text}
          </span>
        ) : (
          <span className="text-green-700 dark:text-green-400">● Rendered OK</span>
        )}
      </span>
      {saveError && (
        <span role="alert" className="text-red-600">
          Save failed: {saveError}
        </span>
      )}
      {dirty && <span className="text-amber-600" title="Differs from what is saved">● Unsaved changes</span>}
      {confirming ? (
        <span className="flex items-center gap-1">
          Discard your saved edit?
          <button
            className={`${btn} bg-red-600 text-white`}
            onClick={() => {
              setConfirming(false);
              onReset();
            }}
          >
            Discard
          </button>
          <button className={btn} onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </span>
      ) : (
        <button
          className={btn}
          disabled={!canReset}
          title="Back to the generated diagram"
          onClick={() => (hasSavedEdit ? setConfirming(true) : onReset())}
        >
          Reset
        </button>
      )}
      <button className={btn} disabled={!dirty || saving} onClick={onSave}>
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
