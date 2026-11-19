import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import DiagramWorkspace from "./DiagramWorkspace";

// Real layout/editor are covered elsewhere; here: the workflow around them.
vi.mock("./CodePane", () => ({
  default: ({ value, onChange, readOnly }: { value: string; onChange: (v: string) => void; readOnly?: boolean }) => (
    <textarea aria-label="editor" value={value} readOnly={readOnly} onChange={(e) => onChange(e.target.value)} />
  ),
}));
vi.mock("./DiagramPane", () => ({
  default: ({ text, fitKey, onResult }: { text: string; fitKey: string; onResult: (e: string | null) => void }) => (
    <div>
      <pre data-testid="rendered">{text}</pre>
      <span data-testid="fitkey">{fitKey}</span>
      <button onClick={() => onResult("Parse error on line 4:\n^\nExpecting X")}>fail render</button>
      <button onClick={() => onResult(null)}>ok render</button>
    </div>
  ),
}));

type View = { generated: string; edited: string | null; nodes: number; edges: number; hubs?: number };
let record: Record<string, unknown>;
let views: Record<string, View>;
let calls: { method: string; url: string; body?: string }[];
let delay: Promise<void> | null;

const baseRecord = () => ({
  id: "d1", owner: "o", name: "r", commit_sha: "a".repeat(40), container_count: 2, component_count: 30,
  max_depth: 3, auto_depth: 2, saved_edits: [], warnings: ["Unsupported language(s): go (3 files)."],
  mermaid_c4: "c4 stored", mermaid_flowchart: "flow stored",
  model: { externals: [{}], containers: [], relations: [], warnings: [], system_name: "r" },
});

const viewFor = (format: string, depth: number): View =>
  (views[`${format}:${depth}`] ??= {
    generated: `${format} generated d${depth}`,
    edited: null,
    nodes: depth * 10,
    edges: depth * 12,
  });

function installFetch() {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body as string | undefined });
      const m = /\/(views|edits)\/(c4|flowchart)\/(\d+)$/.exec(url);
      if (!m) return new Response(JSON.stringify(record));
      if (delay && m[1] === "views") await delay;
      const [, , format, d] = m;
      const v = viewFor(format, Number(d));
      if (method === "PUT") v.edited = JSON.parse(init!.body as string).text;
      if (method === "DELETE") v.edited = null;
      return new Response(JSON.stringify({ format, depth: Number(d), ...v }));
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
const ready = async () => {
  await screen.findByText("o/r");
  await waitFor(() => expect(editor().value).not.toBe(""));
};
const depthBtn = (n: number) => screen.getByRole("button", { name: new RegExp(`^${n}`) });

beforeEach(() => {
  localStorage.clear();
  record = baseRecord();
  views = {};
  delay = null;
  installFetch();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("opens on the flowchart at the default depth, with summary, size and warnings", async () => {
  mount();
  await ready();
  expect(editor().value).toBe("flowchart generated d2");
  expect(rendered()).toBe("flowchart generated d2");
  expect(screen.getByRole("tab", { name: "Flowchart" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText(/30 components/)).toBeInTheDocument();
  expect(screen.getByTestId("view-size")).toHaveTextContent("showing 20 components · 24 relations");
  expect(screen.getByText(/Unsupported language/)).toBeInTheDocument();
  expect(depthBtn(2)).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Save")).toBeDisabled();
  expect(screen.getByText("Reset")).toBeDisabled();
  expect(calls.find((c) => c.url.includes("/views/"))!.url).toBe("/api/diagrams/d1/views/flowchart/2");
});

test("typing marks dirty at once but re-renders the diagram only after a pause", async () => {
  mount();
  await ready();
  type("edit 1");
  type("edit 2");
  expect(editor().value).toBe("edit 2");
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
  expect(rendered()).toBe("flowchart generated d2");
  act(() => vi.advanceTimersByTime(399));
  expect(rendered()).toBe("flowchart generated d2");
  act(() => vi.advanceTimersByTime(2));
  expect(rendered()).toBe("edit 2");
});

test("Save stores the edit for this format and depth only", async () => {
  mount();
  await ready();
  type("my fix");
  fireEvent.click(screen.getByText("Save"));
  await waitFor(() => expect(screen.queryByText(/Unsaved changes/)).toBeNull());
  const put = calls.find((c) => c.method === "PUT")!;
  expect(put.url).toBe("/api/diagrams/d1/edits/flowchart/2");
  expect(JSON.parse(put.body!)).toEqual({ text: "my fix" });
  expect(editor().value).toBe("my fix");
  expect(screen.getByText("Reset")).toBeEnabled();
  expect(screen.getByText("Save")).toBeDisabled();
});

test("a saved edit is what opens next time", async () => {
  views["flowchart:2"] = { generated: "flowchart generated d2", edited: "earlier fix", nodes: 20, edges: 24 };
  mount();
  await ready();
  expect(editor().value).toBe("earlier fix");
  expect(screen.queryByText(/Unsaved changes/)).toBeNull();
  expect(screen.getByText("Reset")).toBeEnabled();
});

test("Reset on an unsaved draft is local; on a saved edit it asks, then discards on the server", async () => {
  mount();
  await ready();
  type("draft");
  fireEvent.click(screen.getByText("Reset"));
  expect(editor().value).toBe("flowchart generated d2");
  expect(calls.some((c) => c.method === "DELETE")).toBe(false);

  views["flowchart:2"].edited = "earlier fix";
  fireEvent.click(screen.getByRole("tab", { name: "C4" }));
  await waitFor(() => expect(editor().value).toBe("c4 generated d2"));
  fireEvent.click(screen.getByRole("tab", { name: "Flowchart" })); // reload that view
  await waitFor(() => expect(editor().value).toBe("earlier fix"));
  fireEvent.click(screen.getByText("Reset"));
  expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  fireEvent.click(screen.getByText("Discard"));
  await waitFor(() => expect(editor().value).toBe("flowchart generated d2"));
  expect(calls.find((c) => c.method === "DELETE")!.url).toBe("/api/diagrams/d1/edits/flowchart/2");
});

test("each format and each depth keeps its own text", async () => {
  mount();
  await ready();
  type("flow d2 draft");
  fireEvent.click(screen.getByRole("tab", { name: "C4" }));
  await waitFor(() => expect(editor().value).toBe("c4 generated d2"));
  type("c4 d2 draft");

  fireEvent.click(depthBtn(3));
  await waitFor(() => expect(editor().value).toBe("c4 generated d3")); // a different view
  expect(screen.getByTestId("view-size")).toHaveTextContent("showing 30 components");
  fireEvent.click(depthBtn(2));
  await waitFor(() => expect(editor().value).toBe("c4 d2 draft")); // the draft survived

  fireEvent.click(screen.getByRole("tab", { name: "Flowchart" }));
  await waitFor(() => expect(editor().value).toBe("flow d2 draft"));
});

test("changing depth renders at once, refits, and is read-only until the view loads", async () => {
  mount();
  await ready();
  let release!: () => void;
  delay = new Promise((r) => (release = r));
  fireEvent.click(depthBtn(3));
  await waitFor(() => expect(editor().readOnly).toBe(true));
  expect(editor().value).toBe("flowchart generated d2"); // previous view stays on screen
  expect(screen.getByTestId("view-size")).toHaveTextContent("loading");
  expect(screen.getByText("Save")).toBeDisabled();
  type("ignored while loading");
  expect(editor().value).toBe("flowchart generated d2");

  release();
  await waitFor(() => expect(editor().readOnly).toBe(false));
  expect(editor().value).toBe("flowchart generated d3");
  expect(rendered()).toBe("flowchart generated d3"); // no 400ms wait on a new view
  expect(screen.getByTestId("fitkey")).toHaveTextContent("d1:flowchart:3");
});

test("tells the user when shared modules were drawn once instead of wired", async () => {
  views["flowchart:2"] = { generated: "g", edited: null, nodes: 40, edges: 30, hubs: 3 };
  views["c4:2"] = { generated: "c", edited: null, nodes: 40, edges: 90, hubs: 0 };
  mount();
  await ready();
  expect(screen.getByTestId("hub-note")).toHaveTextContent("3 shared modules not wired");
  expect(screen.getByTestId("hub-note").getAttribute("title")).toMatch(/C4 tab draws every edge/);
  fireEvent.click(screen.getByRole("tab", { name: "C4" }));
  await waitFor(() => expect(editor().value).toBe("c"));
  expect(screen.queryByTestId("hub-note")).toBeNull(); // C4 draws every edge
});

test("depth is not offered for a flat model", async () => {
  record = { ...baseRecord(), max_depth: 1, auto_depth: 1 };
  mount();
  await ready();
  expect(screen.queryByRole("group", { name: "Depth" })).toBeNull();
});

test("many levels use a dropdown, and the default level is marked", async () => {
  record = { ...baseRecord(), max_depth: 12, auto_depth: 5 };
  mount();
  await ready();
  const select = screen.getByLabelText("Depth level") as HTMLSelectElement;
  expect(select.value).toBe("5");
  expect(screen.getByRole("option", { name: "5 (default)" })).toBeInTheDocument();
  fireEvent.change(select, { target: { value: "9" } });
  await waitFor(() => expect(editor().value).toBe("flowchart generated d9"));
});

test("warns when a view is too big to read comfortably", async () => {
  views["flowchart:2"] = { generated: "huge", edited: null, nodes: 400, edges: 900 };
  mount();
  await ready();
  expect(screen.getByText(/400 components and may be slow/)).toBeInTheDocument();
  fireEvent.click(depthBtn(1));
  await waitFor(() => expect(screen.queryByText(/may be slow/)).toBeNull());
});

test("a render error shows its line; fixing it clears it", async () => {
  mount();
  await ready();
  type("broken");
  fireEvent.click(screen.getByText("fail render"));
  expect(screen.getByRole("status")).toHaveTextContent("Line 4");
  expect(screen.queryByText("The C4 diagram could not be rendered.")).toBeNull();
  fireEvent.click(screen.getByText("ok render"));
  expect(screen.getByRole("status")).toHaveTextContent("Rendered OK");
});

test("when the generated C4 itself fails, the flowchart is offered", async () => {
  mount();
  await ready();
  fireEvent.click(screen.getByRole("tab", { name: "C4" }));
  await waitFor(() => expect(editor().value).toBe("c4 generated d2"));
  fireEvent.click(screen.getByText("fail render"));
  fireEvent.click(await screen.findByText("Show flowchart instead"));
  await waitFor(() => expect(editor().value).toBe("flowchart generated d2"));
  expect(screen.getByRole("tab", { name: "Flowchart" })).toHaveAttribute("aria-selected", "true");
});

test("a failed save is reported and the draft is kept", async () => {
  mount();
  await ready();
  type("my fix");
  (fetch as ReturnType<typeof vi.fn>).mockImplementationOnce(
    async () => new Response(JSON.stringify({ error: { code: "X", message: "disk full" } }), { status: 500 }),
  );
  fireEvent.click(screen.getByText("Save"));
  expect(await screen.findByRole("alert")).toHaveTextContent("disk full");
  expect(editor().value).toBe("my fix");
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
});

test("a view that fails to load is reported", async () => {
  (globalThis as { fetch?: unknown }).fetch = undefined;
  installFetch();
  const real = fetch as ReturnType<typeof vi.fn>;
  real.mockImplementation(async (url: string) =>
    /\/views\//.test(url)
      ? new Response(JSON.stringify({ error: { code: "INVALID_DEPTH", message: "Depth must be between 1 and 3." } }), { status: 422 })
      : new Response(JSON.stringify(record)),
  );
  mount();
  expect(await screen.findByText(/Could not load this view: Depth must be between 1 and 3/)).toBeInTheDocument();
});
