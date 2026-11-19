import { act, renderHook, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { useGenerate } from "./useGenerate";

class FakeES {
  static last: FakeES;
  static CLOSED = 2;
  readyState = 1;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  constructor(public url: string) {
    FakeES.last = this;
  }
  addEventListener(t: string, f: (e: MessageEvent) => void) {
    (this.listeners[t] ??= []).push(f);
  }
  close() {
    this.readyState = 2;
  }
  emit(t: string, data: unknown) {
    this.listeners[t]?.forEach((f) => f({ data: JSON.stringify(data) } as MessageEvent));
  }
}

beforeEach(() => vi.stubGlobal("EventSource", FakeES));

test("stages then done", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ jobId: "j1" }))));
  const { result } = renderHook(() => useGenerate());
  await act(() => result.current.start({ url: "o/r" }));
  await waitFor(() => expect(FakeES.last.url).toBe("/api/jobs/j1/events"));

  act(() => FakeES.last.emit("stage", { stage: "cloning", message: "Cloning o/r" }));
  expect(result.current.state).toMatchObject({ status: "running", stages: [{ stage: "cloning" }] });

  act(() =>
    FakeES.last.emit("done", { diagramId: "d9", repo: "o/r", commit: "a".repeat(40), files: 2 }),
  );
  expect(result.current.state).toMatchObject({ status: "done", diagramId: "d9" });
});

test("server error event and API error", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ jobId: "j2" }))));
  const { result } = renderHook(() => useGenerate());
  await act(() => result.current.start({ url: "o/r" }));
  act(() => FakeES.last.emit("error", { code: "REPO_NOT_FOUND", message: "Repository not found." }));
  expect(result.current.state).toMatchObject({ status: "error", error: { code: "REPO_NOT_FOUND" } });

  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ error: { code: "INVALID_URL", message: "bad" } }), { status: 400 })),
  );
  await act(() => result.current.start({ url: "x" }));
  expect(result.current.state).toMatchObject({ status: "error", error: { code: "INVALID_URL", message: "bad" } });
});

test("an existing diagram is reused without opening a job stream", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ diagramId: "old" }))));
  const created = vi.fn();
  vi.stubGlobal("EventSource", class { constructor() { created(); } });
  const { result } = renderHook(() => useGenerate());
  await act(() => result.current.start({ url: "o/r" }));
  expect(result.current.state).toMatchObject({ status: "done", diagramId: "old", result: null });
  expect(created).not.toHaveBeenCalled();
  act(() => result.current.reset());
  expect(result.current.state.status).toBe("idle");
});
