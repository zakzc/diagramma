import { render, waitFor } from "@testing-library/react";
import { vi } from "vitest";

const mm = vi.hoisted(() => ({ render: vi.fn(), initialize: vi.fn() }));
vi.mock("mermaid", () => ({ default: mm }));

import MermaidView from "./MermaidView";

const svg = (label: string) => ({ svg: `<svg data-label="${label}"></svg>` });

beforeEach(() => {
  mm.render.mockReset();
  mm.initialize.mockReset();
});

test("renders, reports success, and passes the theme", async () => {
  mm.render.mockResolvedValue(svg("one"));
  const onResult = vi.fn();
  const onRendered = vi.fn();
  const { getByTestId } = render(<MermaidView text="a" dark onResult={onResult} onRendered={onRendered} />);
  await waitFor(() => expect(onResult).toHaveBeenCalledWith(null));
  expect(getByTestId("mermaid-output").innerHTML).toContain('data-label="one"');
  expect(onRendered).toHaveBeenCalled();
  expect(mm.initialize).toHaveBeenCalledWith(
    expect.objectContaining({ theme: "dark", securityLevel: "strict", suppressErrorRendering: true }),
  );
});

test("a failed render keeps the last good diagram and reports the error", async () => {
  mm.render.mockResolvedValueOnce(svg("good")).mockRejectedValueOnce(new Error("Parse error on line 2"));
  const onResult = vi.fn();
  const { getByTestId, rerender } = render(<MermaidView text="good" onResult={onResult} />);
  await waitFor(() => expect(onResult).toHaveBeenLastCalledWith(null));

  rerender(<MermaidView text="broken" onResult={onResult} />);
  await waitFor(() => expect(onResult).toHaveBeenLastCalledWith("Parse error on line 2"));
  expect(getByTestId("mermaid-output").innerHTML).toContain('data-label="good"'); // still there

  mm.render.mockResolvedValueOnce(svg("fixed"));
  rerender(<MermaidView text="fixed" onResult={onResult} />);
  await waitFor(() => expect(onResult).toHaveBeenLastCalledWith(null));
  expect(getByTestId("mermaid-output").innerHTML).toContain('data-label="fixed"');
});

test("a slow stale render cannot overwrite a newer one", async () => {
  let release!: (v: { svg: string }) => void;
  mm.render.mockImplementationOnce(() => new Promise((r) => (release = r))).mockResolvedValueOnce(svg("new"));
  const { getByTestId, rerender } = render(<MermaidView text="old" />);
  rerender(<MermaidView text="new" />);
  await waitFor(() => expect(getByTestId("mermaid-output").innerHTML).toContain("new"));
  release(svg("old"));
  await new Promise((r) => setTimeout(r, 10));
  expect(getByTestId("mermaid-output").innerHTML).toContain('data-label="new"');
});
