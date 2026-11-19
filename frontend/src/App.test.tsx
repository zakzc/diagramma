import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import App from "./App";

vi.mock("./components/DiagramWorkspace", () => ({
  default: ({ diagramId }: { diagramId: string }) => <div>diagram {diagramId}</div>,
}));

const summary = (id: string, name: string) => ({
  id, repo_url: `https://github.com/o/${name}`, owner: "o", name, ref: null,
  commit_sha: "a".repeat(40), created_at: "2026-01-02T00:00:00+00:00",
  container_count: 1, component_count: 3, tool_version: "0.1.0",
});
const record = (id: string, name: string) => ({
  ...summary(id, name), mermaid_c4: "C4Component", mermaid_flowchart: "flowchart LR", warnings: [],
  edited_c4: null, edited_flowchart: null,
  model: { system_name: name, containers: [], externals: [], relations: [], warnings: [] },
});

function stubApi(history = [summary("d1", "one")]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
      if (url === "/api/health") return json({ status: "ok", version: "0.1.0" });
      if (url === "/api/diagrams" && !init) return json(history);
      if (url === "/api/diagrams" && init?.method === "POST") return json({ diagramId: "d1" });
      const m = /^\/api\/diagrams\/(\w+)$/.exec(url);
      if (m && init?.method === "DELETE") return new Response(null, { status: 204 });
      if (m) return json(record(m[1], "one"));
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
}

const renderApp = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <App />
    </QueryClientProvider>,
  );

beforeEach(() => localStorage.clear());

test("shows the empty state and the history list", async () => {
  stubApi();
  renderApp();
  expect(screen.getByText("Diagramma")).toBeInTheDocument();
  expect(screen.getByText(/Paste a GitHub repo URL/)).toBeInTheDocument();
  expect(await screen.findByText("o/one")).toBeInTheDocument();
});

test("opening a history entry shows its diagram", async () => {
  stubApi();
  renderApp();
  fireEvent.click(await screen.findByText("o/one"));
  expect(await screen.findByText("diagram d1")).toBeInTheDocument();
});

test("re-submitting a known repo opens the existing diagram", async () => {
  stubApi();
  renderApp();
  fireEvent.change(screen.getByLabelText("GitHub repo URL"), { target: { value: "o/one" } });
  fireEvent.click(screen.getByText("Generate"));
  expect(await screen.findByText("diagram d1")).toBeInTheDocument();
});

test("the history sidebar folds and remembers it", async () => {
  stubApi();
  const { unmount } = renderApp();
  await screen.findByText("o/one");
  fireEvent.click(screen.getByLabelText("Hide history"));
  expect(screen.queryByText("o/one")).not.toBeVisible();
  expect(localStorage.getItem("diagramma.history.collapsed")).toBe("1");
  unmount();
  renderApp();
  expect(screen.getByLabelText("Show history")).toBeInTheDocument();
});

test("deleting asks for confirmation and clears the open diagram", async () => {
  stubApi();
  renderApp();
  fireEvent.click(await screen.findByText("o/one"));
  await screen.findByText("diagram d1");
  fireEvent.click(screen.getByLabelText("Delete o/one"));
  fireEvent.click(screen.getByText("Delete"));
  await waitFor(() => expect(screen.queryByText("diagram d1")).toBeNull());
  expect(screen.getByText(/Paste a GitHub repo URL/)).toBeInTheDocument();
});

test("on a narrow screen the history starts folded unless the user chose otherwise", async () => {
  stubApi();
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: q.includes("max-width"),
    addEventListener() {},
    removeEventListener() {},
  }));
  const { unmount } = renderApp();
  expect(screen.getByLabelText("Show history")).toBeInTheDocument();
  unmount();
  localStorage.setItem("diagramma.history.collapsed", "0"); // an explicit choice wins
  renderApp();
  expect(screen.getByLabelText("Hide history")).toBeInTheDocument();
  vi.unstubAllGlobals();
});
