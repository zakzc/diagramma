import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import StatusBar, { summarizeError } from "./StatusBar";

const base = {
  error: null, dirty: false, canReset: false, hasSavedEdit: false,
  saving: false, saveError: null, onSave: () => {}, onReset: () => {},
};

test("summarizes Mermaid parse errors with their line number", () => {
  const msg = "Parse error on line 12:\n...Rel(a, b\n------^\nExpecting 'STR', got 'EOF'";
  expect(summarizeError(msg)).toEqual({ line: 12, text: "Expecting 'STR', got 'EOF'" });
  expect(summarizeError("Parse error on line 7: unexpected end")).toEqual({ line: 7, text: "unexpected end" });
  expect(summarizeError("Something odd")).toEqual({ line: null, text: "Something odd" });
});

test("shows OK, then the error with its line", () => {
  const { rerender } = render(<StatusBar {...base} />);
  expect(screen.getByRole("status")).toHaveTextContent("Rendered OK");
  rerender(<StatusBar {...base} error={"Parse error on line 3:\nx\nExpecting y"} />);
  expect(screen.getByRole("status")).toHaveTextContent("Line 3");
  expect(screen.queryByText(/Rendered OK/)).toBeNull();
});

test("Save needs unsaved changes; the dirty marker shows", () => {
  const onSave = vi.fn();
  const { rerender } = render(<StatusBar {...base} onSave={onSave} />);
  expect(screen.getByText("Save")).toBeDisabled();
  expect(screen.queryByText(/Unsaved changes/)).toBeNull();
  rerender(<StatusBar {...base} dirty onSave={onSave} />);
  expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Save"));
  expect(onSave).toHaveBeenCalled();
});

test("Reset is immediate for a draft but asks before discarding a saved edit", () => {
  const onReset = vi.fn();
  const { rerender } = render(<StatusBar {...base} canReset onReset={onReset} />);
  fireEvent.click(screen.getByText("Reset"));
  expect(onReset).toHaveBeenCalledTimes(1);

  rerender(<StatusBar {...base} canReset hasSavedEdit onReset={onReset} />);
  fireEvent.click(screen.getByText("Reset"));
  expect(onReset).toHaveBeenCalledTimes(1); // not yet
  fireEvent.click(screen.getByText("Cancel"));
  fireEvent.click(screen.getByText("Reset"));
  fireEvent.click(screen.getByText("Discard"));
  expect(onReset).toHaveBeenCalledTimes(2);
});

test("a failed save is shown", () => {
  render(<StatusBar {...base} dirty saveError="boom" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Save failed: boom");
});
