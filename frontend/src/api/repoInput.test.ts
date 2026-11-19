import { validateRepoInput } from "./repoInput";

test.each(["https://github.com/o/r", "https://github.com/o/r.git", "o/r"])(
  "accepts %s",
  (u) => expect(validateRepoInput(u, "").ok).toBe(true),
);

test.each(["", "http://github.com/o/r", "https://gitlab.com/o/r", "o", "../r", "o/..", "git@github.com:o/r.git"])(
  "rejects %j",
  (u) => expect(validateRepoInput(u, "").ok).toBe(false),
);

test("ref handling", () => {
  expect(validateRepoInput("o/r", " feature/x ")).toEqual({ ok: true, value: { url: "o/r", ref: "feature/x" } });
  expect(validateRepoInput("o/r", "").ok && (validateRepoInput("o/r", "") as any).value.ref).toBeUndefined();
  expect(validateRepoInput("o/r", "-evil").ok).toBe(false);
  expect(validateRepoInput("o/r", "a..b").ok).toBe(false);
});
