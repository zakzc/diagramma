import { act, fireEvent, render, screen } from "@testing-library/react";
import { forwardRef, useImperativeHandle } from "react";
import { vi } from "vitest";

const zoom = vi.hoisted(() => ({ fitToView: vi.fn(), zoomIn: vi.fn(), zoomOut: vi.fn() }));
vi.mock("react-zoom-pan-pinch", () => ({
  TransformWrapper: forwardRef(({ children }: { children: React.ReactNode }, ref) => {
    useImperativeHandle(ref, () => zoom);
    return <div>{children}</div>;
  }),
  TransformComponent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("./MermaidView", () => ({
  default: ({ text, onRendered }: { text: string; onRendered?: (s: SVGSVGElement) => void }) => (
    <button onClick={() => onRendered?.(document.createElementNS("http://www.w3.org/2000/svg", "svg"))}>
      render:{text}
    </button>
  ),
}));

import DiagramPane from "./DiagramPane";

beforeEach(() => {
  vi.useFakeTimers();
  zoom.fitToView.mockClear();
});
afterEach(() => vi.useRealTimers());

test("fits once per diagram/format, not on every re-render while typing", () => {
  const { rerender } = render(<DiagramPane text="a" fitKey="d1:c4" onResult={() => {}} />);
  fireEvent.click(screen.getByText("render:a"));
  act(() => vi.advanceTimersByTime(50));
  expect(zoom.fitToView).toHaveBeenCalledTimes(1);

  rerender(<DiagramPane text="ab" fitKey="d1:c4" onResult={() => {}} />);
  fireEvent.click(screen.getByText("render:ab"));
  act(() => vi.advanceTimersByTime(50));
  expect(zoom.fitToView).toHaveBeenCalledTimes(1); // the user's pan/zoom is kept

  rerender(<DiagramPane text="f" fitKey="d1:flowchart" onResult={() => {}} />);
  fireEvent.click(screen.getByText("render:f"));
  act(() => vi.advanceTimersByTime(50));
  expect(zoom.fitToView).toHaveBeenCalledTimes(2);
});

test("toolbar: zoom, fit, and copy the displayed text", async () => {
  const writeText = vi.fn(async () => {});
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  render(<DiagramPane text="C4Component" fitKey="k" onResult={() => {}} />);
  fireEvent.click(screen.getByLabelText("Zoom in"));
  fireEvent.click(screen.getByLabelText("Zoom out"));
  fireEvent.click(screen.getByText("Fit"));
  expect(zoom.zoomIn).toHaveBeenCalled();
  expect(zoom.zoomOut).toHaveBeenCalled();
  expect(zoom.fitToView).toHaveBeenCalledWith({ animationTime: 0 });

  await act(async () => fireEvent.click(screen.getByText("Copy .mmd")));
  expect(writeText).toHaveBeenCalledWith("C4Component");
  expect(screen.getByText("Copied")).toBeInTheDocument();
  vi.unstubAllGlobals();
});
