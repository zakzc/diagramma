# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Diagramma: paste a GitHub repo URL, the Python backend statically analyses it, and the React frontend renders the result as Mermaid diagrams. Repo code is never executed or installed. [README.md](README.md) has the overview, API table, env vars and known limits; [SPEC.md](SPEC.md) is the authoritative design (it wins over the README when they disagree); [progress.md](progress.md) is the milestone checklist and log of every deviation. The README has not yet been updated for the Imports view (M9, SPEC §9.4).

## Working instructions

- Always consult `docs/architecture.md` (not created yet; [SPEC.md](SPEC.md) plays that role for now) and [progress.md](progress.md).
- Make the smallest correct change. Prefer simple, idiomatic solutions.
- Reuse existing code, types, utilities and dependencies. Follow existing project patterns; inspect the relevant code before changing it.
- Avoid unnecessary abstractions, refactors, dependencies and comments.
- Fix root causes, not symptoms.
- If something cannot be answered or implemented, say so and give the reason; do not give a nonsensical answer.
- When implementing a spec, create or update progress.md (what was done, what is in progress, what remains), and make one git commit per completed step, with a message that traces back to the spec (section or milestone).
- Do not pull in SPEC §12 roadmap items without updating the spec first; record deviations in SPEC.md and progress.md.
- In spec files, number every Open Question so they can be addressed by number.

## Output

- Be concise. Do not repeat the request or summarize unchanged code.
- At the end of each task, list all files that were changed.

## Commands

Backend (`backend/`, Python 3.12 pinned, managed with `uv`):
```bash
uv sync
uv run python -m app                      # API + built frontend on 127.0.0.1:8787
uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload   # dev
uv run pytest                             # all tests
uv run pytest tests/test_layering.py::test_name -q   # a single test
uv run ruff check . && uv run ruff format .          # line length 100
```

Frontend (`frontend/`):
```bash
npm ci
npm run dev                # Vite on :5173, proxies /api to :8787 (start the backend too)
npm test                   # vitest run (all)
npx vitest run src/components/DiagramWorkspace.test.tsx -t "Imports"   # one file / test name
npm run build              # tsc -b (strict) + vite build -> frontend/dist
npm run gen:api            # regenerate src/api/schema.d.ts from FastAPI's OpenAPI (no server needed)
```

## Architecture

**Pipeline.** `jobs/pipeline.py` runs in a process pool: fetch (shallow `git fetch`) → `analysis/scan.py` → `analysis/build.py` (`build_model`) → render. Stages talk only through the Pydantic `Model` in `models.py`. `build_model` chains containers → externals → components → `graph.py` (tree-sitter imports resolved to files/containers/externals) → `relations.py` → `reduce.py`, and `files.py` (React file model, M9). One `used` id set is shared by containers, components, externals and files so Mermaid ids never collide.

**Model and views.** The whole `Model` is stored as JSON with each diagram (`db.py`, SQLite). Only the default-depth C4/flowchart texts are stored; every other view is rendered on demand from the model by `GET /api/diagrams/{id}/views/{format}/{depth}` (`api/routes.py::_generated`). Components form a tree per container, relations are stored between leaves, and `render/view.py::build_view` rolls them up to a depth. Formats: `c4`, `flowchart`, `layers` (layered dependency graph, `analysis/layering.py` + `render/layers.py`), `imports` (React file graph, `analysis/filekind.py` + `render/imports.py`; ignores depth, the UI pins it to depth 1).

**Adding a view format** touches several places: `ViewFormat` and the summary model in `models.py`, a branch in `routes.py::_generated`, a renderer in `render/`, `EditFormat`/tab in the frontend (`api/client.ts`, `useDiagramEditor.ts`, `DiagramWorkspace.tsx`), then `npm run gen:api`. User edits are stored per (diagram, format, depth) in the `edits` table; the SQL does not restrict `format`, the API validates it.

**Versioning.** `app.__version__` (also in `pyproject.toml`) marks the generated output. A resubmit at the same commit reuses the stored diagram only if the tool version matches; otherwise it regenerates. Bump it when the stored model gains fields, and make views on older records answer a `409 *_UNAVAILABLE` error (see `LAYERS_UNAVAILABLE`, `IMPORTS_UNAVAILABLE`; codes are mapped to HTTP status in `errors.py`).

**Frontend.** React 18 + TanStack Query. `DiagramWorkspace.tsx` owns the tabs/summary strips; `useDiagramEditor.ts` holds per-view text, drafts and saved edits (keyed `format:depth`). Mermaid renders in the browser, on a light canvas, with `securityLevel: "strict"`.

## Conventions that are easy to miss

- Renderers must be **deterministic** (sorted output, no timestamps; the header uses the commit date). Golden files in `backend/tests/golden/` are written on first run if missing and compared afterwards; delete one to regenerate it. `frontend/src/golden-mermaid.test.ts` parses every golden with the pinned Mermaid, and lists required names, so add new goldens there.
- Test repos are built on the fly with `tests/helpers.py::model_of(tmp_path, {path: text})`; an autouse fixture keeps tests off the real history DB and clone cache.
- Never hand-edit `frontend/src/api/schema.d.ts`; regenerate it after any change to backend schemas.
- All text going into Mermaid goes through `render/escape.py` (`make_id`, `label`). `str.format` mangles Mermaid shape braces; use `.replace`.
- TS/JS import resolution does not read `tsconfig` `paths`/`baseUrl`, only relative paths, `index`, `.js`→`.ts` and the `@/`, `~/`, `#/` aliases.
