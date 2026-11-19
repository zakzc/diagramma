import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import CodePane from "./CodePane";

// CodeMirror needs real layout; here we only check our wiring around it.
vi.mock("@uiw/react-codemirror", () => ({
  default: ({ value, onChange, theme }: { value: string; onChange: (v: string) => void; theme: string }) => (
    <textarea aria-label="cm" data-theme={theme} value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

test("shows the text and reports edits", () => {
  const onChange = vi.fn();
  render(<CodePane value="C4Component" onChange={onChange} />);
  const box = screen.getByLabelText("cm") as HTMLTextAreaElement;
  expect(box.value).toBe("C4Component");
  expect(box).toHaveAttribute("data-theme", "light");
  fireEvent.change(box, { target: { value: "C4Component\n  title x" } });
  expect(onChange).toHaveBeenCalledWith("C4Component\n  title x");
});

test("follows the system dark theme", () => {
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  render(<CodePane value="x" onChange={() => {}} />);
  expect(screen.getByLabelText("cm")).toHaveAttribute("data-theme", "dark");
  vi.unstubAllGlobals();
});
