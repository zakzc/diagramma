// Mirrors backend validation (app/analysis/fetch.py) for instant feedback; the server is authoritative.
const NAME = "[A-Za-z0-9_.-]+";
const URL_RE = new RegExp(`^https://github\\.com/(${NAME})/(${NAME})/?$`);
const SHORT_RE = new RegExp(`^(${NAME})/(${NAME})$`);
const REF_RE = /^[A-Za-z0-9_][A-Za-z0-9_./-]*$/;

export type RepoInput = { url: string; ref?: string };

export function validateRepoInput(rawUrl: string, rawRef: string): { ok: true; value: RepoInput } | { ok: false; error: string } {
  const url = rawUrl.trim();
  const m = URL_RE.exec(url) ?? SHORT_RE.exec(url);
  const name = m?.[2].replace(/\.git$/, "");
  if (!m || !name || m[1] === ".." || m[1] === "." || name === ".." || name === ".") {
    return { ok: false, error: "Enter a GitHub repo as https://github.com/owner/repo or owner/repo." };
  }
  const ref = rawRef.trim();
  if (ref && (!REF_RE.test(ref) || ref.includes("..") || ref.endsWith(".lock"))) {
    return { ok: false, error: `'${ref}' is not a valid branch, tag or commit.` };
  }
  return { ok: true, value: { url, ref: ref || undefined } };
}
