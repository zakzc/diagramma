import { act, fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import SplitLayout, { DEFAULT_RATIO, STORAGE_KEY } from "./SplitLayout";

const left = { title: "Mermaid code", body: <div>CODE BODY</div> };
const right = { title: "Diagram", actions: <button>fmt</button>, body: <div>DIAGRAM BODY</div> };
const layout = () => screen.getByTestId("split");
const sep = () => screen.getByRole("separator");
const ratio = () => Number(sep().getAttribute("aria-valuenow"));

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

test("opens as a 1/3 : 2/3 split with both panes visible", () => {
  render(<SplitLayout left={left} right={right} />);
  expect(layout()).toHaveAttribute("data-fold", "split");
  expect(ratio()).toBe(33);
  expect(layout().style.gridTemplateColumns).toMatch(/0\.33\d*fr\) 6px minmax\(0(px)?, 0\.66\d*fr\)/);
  expect(DEFAULT_RATIO).toBeCloseTo(1 / 3);
  expect(screen.getByText("CODE BODY")).toBeVisible();
  expect(screen.getByText("DIAGRAM BODY")).toBeVisible();
  expect(screen.getByText("fmt")).toBeInTheDocument(); // pane header actions
});

test("folding either pane gives code-only or diagram-only, bodies stay mounted", () => {
  render(<SplitLayout left={left} right={right} />);
  fireEvent.click(screen.getByLabelText("Fold Diagram"));
  expect(layout()).toHaveAttribute("data-fold", "code");
  expect(screen.getByText("CODE BODY")).toBeVisible();
  expect(screen.getByText("DIAGRAM BODY")).not.toBeVisible(); // hidden, not unmounted
  expect(screen.queryByRole("separator")).toBeNull();

  fireEvent.click(screen.getByLabelText("Unfold Diagram"));
  expect(layout()).toHaveAttribute("data-fold", "split");

  fireEvent.click(screen.getByLabelText("Fold Mermaid code"));
  expect(layout()).toHaveAttribute("data-fold", "diagram");
  expect(screen.getByText("CODE BODY")).not.toBeVisible();
  expect(screen.getByText("DIAGRAM BODY")).toBeVisible();
});

test("the last open pane cannot be folded", () => {
  render(<SplitLayout left={left} right={right} />);
  fireEvent.click(screen.getByLabelText("Fold Diagram"));
  expect(screen.getByLabelText("Fold Mermaid code")).toBeDisabled();
  fireEvent.click(screen.getByLabelText("Fold Mermaid code"));
  expect(layout()).toHaveAttribute("data-fold", "code");

  fireEvent.click(screen.getByLabelText("Unfold Diagram"));
  fireEvent.click(screen.getByLabelText("Fold Mermaid code"));
  expect(screen.getByLabelText("Fold Diagram")).toBeDisabled();
});

test("dragging the divider resizes, clamped to sensible bounds", () => {
  render(<SplitLayout left={left} right={right} />);
  layout().getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 600 }) as DOMRect;
  fireEvent.pointerDown(sep(), { pointerId: 1, clientX: 333 });
  fireEvent.pointerMove(sep(), { pointerId: 1, clientX: 500 });
  expect(ratio()).toBe(50);
  fireEvent.pointerMove(sep(), { pointerId: 1, clientX: 5 });
  expect(ratio()).toBe(15);
  fireEvent.pointerMove(sep(), { pointerId: 1, clientX: 990 });
  expect(ratio()).toBe(85);
  fireEvent.pointerUp(sep(), { pointerId: 1 });
  fireEvent.pointerMove(sep(), { pointerId: 1, clientX: 300 }); // no longer dragging
  expect(ratio()).toBe(85);
});

test("double-click resets the divider to 1/3", () => {
  render(<SplitLayout left={left} right={right} />);
  fireEvent.keyDown(sep(), { key: "ArrowRight" });
  fireEvent.keyDown(sep(), { key: "ArrowRight" });
  expect(ratio()).toBe(37);
  fireEvent.doubleClick(sep());
  expect(ratio()).toBe(33);
});

test("fold state and divider position persist across reloads", () => {
  const first = render(<SplitLayout left={left} right={right} />);
  fireEvent.keyDown(sep(), { key: "ArrowRight" });
  fireEvent.click(screen.getByLabelText("Fold Diagram"));
  expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toMatchObject({ fold: "code" });
  first.unmount();

  render(<SplitLayout left={left} right={right} />);
  expect(layout()).toHaveAttribute("data-fold", "code");
  fireEvent.click(screen.getByLabelText("Unfold Diagram"));
  expect(ratio()).toBe(35);
});

test("corrupt or hostile stored layout falls back to defaults", () => {
  localStorage.setItem(STORAGE_KEY, '{"fold":"evil","ratio":99}');
  render(<SplitLayout left={left} right={right} />);
  expect(layout()).toHaveAttribute("data-fold", "split");
  expect(ratio()).toBe(85); // clamped, not 99
  localStorage.setItem(STORAGE_KEY, "not json");
});

test("keyboard shortcuts fold panes but never the last one", () => {
  render(<SplitLayout left={left} right={right} />);
  fireEvent.keyDown(window, { altKey: true, code: "Digit1" }); // fold code
  expect(layout()).toHaveAttribute("data-fold", "diagram");
  fireEvent.keyDown(window, { altKey: true, code: "Digit2" }); // would fold the last pane
  expect(layout()).toHaveAttribute("data-fold", "diagram");
  fireEvent.keyDown(window, { altKey: true, code: "Digit1" }); // unfold code
  expect(layout()).toHaveAttribute("data-fold", "split");
  fireEvent.keyDown(window, { altKey: true, code: "Digit2" });
  expect(layout()).toHaveAttribute("data-fold", "code");
});

test("stacks vertically on narrow screens with the same fold behaviour", () => {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: q.includes("max-width"),
    addEventListener() {},
    removeEventListener() {},
  }));
  render(<SplitLayout left={left} right={right} />);
  expect(layout()).toHaveAttribute("data-orientation", "stacked");
  expect(layout().style.gridTemplateRows).toContain("fr");
  expect(sep()).toHaveAttribute("aria-orientation", "horizontal");
  layout().getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 800 }) as DOMRect;
  fireEvent.pointerDown(sep(), { pointerId: 1 });
  fireEvent.pointerMove(sep(), { pointerId: 1, clientY: 400 });
  expect(ratio()).toBe(50);
  fireEvent.click(screen.getByLabelText("Fold Diagram"));
  expect(layout()).toHaveAttribute("data-fold", "code");
});

test("reacts to the viewport changing", () => {
  let on: () => void = () => {};
  let narrow = false;
  vi.stubGlobal("matchMedia", () => ({
    get matches() {
      return narrow;
    },
    addEventListener: (_: string, f: () => void) => (on = f),
    removeEventListener() {},
  }));
  render(<SplitLayout left={left} right={right} />);
  expect(layout()).toHaveAttribute("data-orientation", "side-by-side");
  narrow = true;
  act(() => on());
  expect(layout()).toHaveAttribute("data-orientation", "stacked");
});
