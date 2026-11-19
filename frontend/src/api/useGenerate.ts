import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, createDiagram } from "./client";
import type { RepoInput } from "./repoInput";

export type StageName = "cloning" | "scanning" | "detecting" | "rendering";
export type StageEvent = { stage: StageName; message: string };
export type ScanSummary = {
  diagramId: string | null;
  repo: string;
  ref: string | null;
  commit: string;
  files: number;
  languages: Record<string, number>;
  manifests: string[];
  containers: number;
  components: number;
  warnings: string[];
};
export type JobError = { code: string; message: string };

export type GenerateState =
  | { status: "idle" }
  | { status: "running"; stages: StageEvent[] }
  | { status: "done"; stages: StageEvent[]; diagramId: string; result: ScanSummary | null }
  | { status: "error"; stages: StageEvent[]; error: JobError };

export function useGenerate() {
  const [state, setState] = useState<GenerateState>({ status: "idle" });
  const source = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    source.current?.close();
    source.current = null;
  }, []);
  useEffect(() => close, [close]);

  const reset = useCallback(() => {
    close();
    setState({ status: "idle" });
  }, [close]);

  const start = useCallback(
    async (input: RepoInput) => {
      close();
      const stages: StageEvent[] = [];
      setState({ status: "running", stages });
      let jobId: string | null | undefined;
      try {
        const created = await createDiagram(input);
        if (created.diagramId) {
          // Same repo, ref and commit as an existing diagram: nothing to analyse.
          setState({ status: "done", stages, diagramId: created.diagramId, result: null });
          return;
        }
        jobId = created.jobId;
        if (!jobId) throw new ApiError("NO_JOB", "The server did not return a job.");
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError("NETWORK", "Could not reach the backend.");
        setState({ status: "error", stages, error: { code: err.code, message: err.message } });
        return;
      }

      const es = new EventSource(`/api/jobs/${jobId}/events`);
      source.current = es;
      es.addEventListener("stage", (ev) => {
        stages.push(JSON.parse((ev as MessageEvent).data));
        setState({ status: "running", stages: [...stages] });
      });
      es.addEventListener("done", (ev) => {
        close();
        const result: ScanSummary = JSON.parse((ev as MessageEvent).data);
        if (!result.diagramId) {
          setState({
            status: "error",
            stages: [...stages],
            error: { code: "NO_DIAGRAM", message: "The analysis finished without a diagram." },
          });
          return;
        }
        setState({ status: "done", stages: [...stages], diagramId: result.diagramId, result });
      });
      es.addEventListener("error", (ev) => {
        const data = (ev as MessageEvent).data;
        if (data) {
          close();
          setState({ status: "error", stages: [...stages], error: JSON.parse(data) });
        } else if (es.readyState === EventSource.CLOSED) {
          close();
          setState({
            status: "error",
            stages: [...stages],
            error: { code: "NETWORK", message: "Lost connection to the backend." },
          });
        }
      });
    },
    [close],
  );

  return { state, start, reset };
}
