import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import DiagramWorkspace from "./DiagramWorkspace";

// Real layout/editor are covered elsewhere; here: the workflow around them.
vi.mock("./CodePane", () => ({
  default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <textarea aria-label="editor" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));
vi.mock("./DiagramPane", () => ({
  default: ({ text, onResult }: { text: string; onResult: (e: string | null) => void }) => (
    <div>
      <pre data-testid="rendered">{text}</pre>
      <button onClick={() => onResult("Parse error on line 4:\n^\nExpecting X")}>fail render</button>
      <button onClick={() => onResult(null)}>ok render</button>
    </div>
  ),
}));

type Rec = Record<string, unknown>;
let server: Rec;
let calls: { method: string; url: string; body?: string }[];

const baseRecord = (): Rec => ({
  id: "d1", owner: "o", name: "r", commit_sha: "a".repeat(40), container_count: 2, component_count: 7,
  mermaid_c4: "C4 generated", mermaid_flowchart: "flow generated", edited_c4: null, edited_flowchart: null,
  warnings: ["Unsupported language(s): go (3 files)."],
  model: { externals: [{}], containers: [], relations: [], warnings: [], system_name: "r" },
});

function installFetch() {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body as string | undefined });
      const m = /\/edits\/(c4|flowchart)$/.exec(url);
      if (m && method === "PUT") server[`edited_${m[1]}`] = JSON.parse(init!.body as string).text;
      if (m && method === "DELETE") server[`edited_${m[1]}`] = null;
      return new Response(JSON.stringify(server));
    }),
  );
}

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DiagramWorkspace diagramId="d1" />
    </QueryClientProvider>,
  );
const editor = () => screen.getByLabelText("editor") as HTMLTextAreaElement;
const rendered = () => screen.getByTestId("rendered").textContent;
const type = (v: string) => fireEvent.change(editor(), { target: { value: v } });

beforeEach(() => {
  localStorage.clear();
  server = baseRecord();
  installFetch();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("opens with the generated C4 text, summary and warnings", async () => {
  mount();
  expect(await screen.findByText("o/r")).toBeInTheDocument();
  expect(screen.getByText(/7 components/)).toBeInTheDocument();
  expect(screen.getByText(/Unsupported language/)).toBeInTheDocument();
  expect(editor().value).toBe("C4 generated");
  expect(rendered()).toBe("C4 generated");
  expect(screen.getByText("Save")).toBeDisabled();
  expect(screen.getByText("Reset")).toBeDisabled();
});

test("typing marks dirty at once but re-renders the diagram only after a pause", async () => {
  mount();
  await screen.findByText("o/r");
  type("C4 edit 1");
  type("C4 edit 2");
  expect(editor().value).toBe("C4 edit 2");
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
  expect(rendered()).toBe("C4 generated"); // not yet
  act(() => vi.advanceTimersByTime(399));
  expect(rendered()).toBe("C4 generated");
  act(() => vi.advanceTimersByTime(2));
  expect(rendered()).toBe("C4 edit 2"); // one render for the burst
});

test("Save stores the edit on the entry; it then reads as saved, not dirty", async () => {
  mount();
  await screen.findByText("o/r");
  type("my fix");
  fireEvent.click(screen.getByText("Save"));
  await waitFor(() => expect(screen.queryByText(/Unsaved changes/)).toBeNull());
  const put = calls.find((c) => c.method === "PUT")!;
  expect(put.url).toBe("/api/diagrams/d1/edits/c4");
  expect(JSON.parse(put.body!)).toEqual({ text: "my fix" });
  expect(editor().value).toBe("my fix");
  expect(screen.getByText("Reset")).toBeEnabled(); // differs from the generated text
  expect(screen.getByText("Save")).toBeDisabled();
});

test("a saved edit is what opens next time", async () => {
  server.edited_c4 = "earlier fix";
  mount();
  await screen.findByText("o/r");
  expect(editor().value).toBe("earlier fix");
  expect(screen.queryByText(/Unsaved changes/)).toBeNull();
  expect(screen.getByText("Reset")).toBeEnabled();
});

test("Reset on an unsaved draft is local and restores the generated text", async () => {
  mount();
  await screen.findByText("o/r");
  type("draft");
  fireEvent.click(screen.getByText("Reset"));
  expect(editor().value).toBe("C4 generated");
  expect(calls.some((c) => c.method === "DELETE")).toBe(false);
});

test("Reset of a saved edit asks, then discards it on the server", async () => {
  server.edited_c4 = "earlier fix";
  mount();
  await screen.findByText("o/r");
  fireEvent.click(screen.getByText("Reset"));
  expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  fireEvent.click(screen.getByText("Discard"));
  await waitFor(() => expect(editor().value).toBe("C4 generated"));
  expect(calls.find((c) => c.method === "DELETE")!.url).toBe("/api/diagrams/d1/edits/c4");
});

test("each format keeps its own edits", async () => {
  mount();
  await screen.findByText("o/r");
  type("c4 draft");
  fireEvent.click(screen.getByRole("tab", { name: "Flowchart" }));
  expect(editor().value).toBe("flow generated");
  expect(rendered()).toBe("flow generated"); // switching tabs renders at once
  type("flow draft");
  fireEvent.click(screen.getByRole("tab", { name: "C4" }));
  expect(editor().value).toBe("c4 draft");
  fireEvent.click(screen.getByRole("tab", { name: "Flowchart" }));
  expect(editor().value).toBe("flow draft");
});

test("a render error shows its line; fixing it clears it", async () => {
  mount();
  await screen.findByText("o/r");
  type("broken");
  fireEvent.click(screen.getByText("fail render"));
  expect(screen.getByRole("status")).toHaveTextContent("Line 4");
  expect(screen.queryByText("The C4 diagram could not be rendered.")).toBeNull(); // user's own edit
  fireEvent.click(screen.getByText("ok render"));
  expect(screen.getByRole("status")).toHaveTextContent("Rendered OK");
});

test("when the generated C4 itself fails, the flowchart is offered", async () => {
  mount();
  await screen.findByText("o/r");
  fireEvent.click(screen.getByText("fail render"));
  fireEvent.click(await screen.findByText("Show flowchart instead"));
  expect(editor().value).toBe("flow generated");
  expect(screen.getByRole("tab", { name: "Flowchart" })).toHaveAttribute("aria-selected", "true");
});

test("a failed save is reported and the draft is kept", async () => {
  mount();
  await screen.findByText("o/r");
  type("my fix");
  (fetch as ReturnType<typeof vi.fn>).mockImplementationOnce(
    async () => new Response(JSON.stringify({ error: { code: "X", message: "disk full" } }), { status: 500 }),
  );
  // the first mocked call is the PUT because the record is already cached
  fireEvent.click(screen.getByText("Save"));
  expect(await screen.findByRole("alert")).toHaveTextContent("disk full");
  expect(editor().value).toBe("my fix");
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
});
