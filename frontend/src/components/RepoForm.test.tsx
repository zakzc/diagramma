import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import RepoForm from "./RepoForm";

test("submits a valid repo and blocks an invalid one", () => {
  const onSubmit = vi.fn();
  render(<RepoForm busy={false} onSubmit={onSubmit} />);
  const input = screen.getByLabelText("GitHub repo URL");

  fireEvent.change(input, { target: { value: "nope" } });
  fireEvent.click(screen.getByText("Generate"));
  expect(screen.getByRole("alert")).toBeInTheDocument();
  expect(onSubmit).not.toHaveBeenCalled();

  fireEvent.change(input, { target: { value: "owner/repo" } });
  fireEvent.change(screen.getByLabelText("Branch, tag or commit"), { target: { value: "dev" } });
  fireEvent.click(screen.getByText("Generate"));
  expect(onSubmit).toHaveBeenCalledWith({ url: "owner/repo", ref: "dev" });
  expect(screen.queryByRole("alert")).toBeNull();
});

test("disables the button while busy", () => {
  render(<RepoForm busy onSubmit={() => {}} />);
  expect(screen.getByRole("button")).toBeDisabled();
});
