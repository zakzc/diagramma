import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import HistoryList from "./HistoryList";

const row = (id: string, ref: string | null) => ({
  id, repo_url: "u", owner: "o", name: id, ref, commit_sha: "b".repeat(40),
  created_at: "2026-01-02T00:00:00+00:00", container_count: 2, component_count: 9, tool_version: "x",
});

const wrap = (ui: React.ReactNode) =>
  render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

test("lists entries with ref, short sha and counts; selecting calls back", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([row("a", "dev"), row("b", null)]))));
  const onSelect = vi.fn();
  wrap(<HistoryList selectedId="b" onSelect={onSelect} onDeleted={() => {}} />);
  expect(await screen.findByText("o/a")).toBeInTheDocument();
  expect(screen.getByText(/dev · bbbbbbb/)).toBeInTheDocument();
  expect(screen.getAllByText("2 containers · 9 components")).toHaveLength(2);
  fireEvent.click(screen.getByText("o/a"));
  expect(onSelect).toHaveBeenCalledWith("a");
});

test("cancel keeps the entry", async () => {
  const f = vi.fn(async () => new Response(JSON.stringify([row("a", null)])));
  vi.stubGlobal("fetch", f);
  wrap(<HistoryList selectedId={null} onSelect={() => {}} onDeleted={() => {}} />);
  fireEvent.click(await screen.findByLabelText("Delete o/a"));
  fireEvent.click(screen.getByText("Cancel"));
  expect(screen.getByText("o/a")).toBeInTheDocument();
  expect(f).toHaveBeenCalledTimes(1); // only the list request: nothing was deleted
});
