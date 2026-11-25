# Diagramma

Paste a GitHub repo URL (or pick a folder on your machine) and get a C4-style **Component diagram** of the whole application, rendered with Mermaid. Everything runs locally; the only network use is talking to GitHub (`git fetch` / `ls-remote`); a local folder needs no network.

- See how the code is organised as **nested components** (folders, sub-folders, files) and how they depend on each other, at a **depth you choose**.
- Edit the Mermaid code live in a split view (code 1/3, diagram 2/3, either pane foldable).
- Copy the raw Mermaid (`.mmd`) text and use it in any Mermaid viewer.
- Past diagrams are kept in a history list and reopen without re-analysing.

> **Status:** built through M11 (analysis, history, editor, Dependencies and Imports views, local folders, details panel) plus the UI refresh (M13). [SPEC.md](SPEC.md) is the full design, [progress.md](progress.md) the build log with every decision and deviation. If this README and SPEC.md disagree, SPEC.md wins.

---

## Getting started

### 1. Install

You need three tools on the machine. Everything else (Python 3.12 itself, every Python and npm package) is installed by the commands below.

| Tool | Why | Check | Get it |
|---|---|---|---|
| **git** | the backend runs `git fetch` / `ls-remote` for GitHub repos | `git --version` | https://git-scm.com |
| **uv** | installs Python 3.12 and the backend packages | `uv --version` | https://docs.astral.sh/uv/getting-started/installation/ (macOS: `brew install uv`) |
| **Node.js 20.19+** (22 LTS is safe) with npm | installs and builds the frontend (Vite 8) | `node -v` | https://nodejs.org |

Then, once per machine (and again after pulling changes that touch the lock files):

```bash
cd backend  && uv sync --locked     # Python deps from uv.lock (the equivalent of `npm ci`)
cd ../frontend && npm ci            # npm deps from package-lock.json
```

- `uv sync` creates `backend/.venv` and installs exactly what `uv.lock` pins, including the dev tools (pytest, ruff). `--locked` makes it fail instead of silently changing the lock file, like `npm ci`. Add `--no-dev` to skip pytest and ruff.
- `uv` reads `backend/.python-version` (3.12) and downloads that Python if it is missing, so you do not install Python yourself.
- Without `uv`: `python3.12 -m venv backend/.venv && backend/.venv/bin/pip install -e backend` also works (it reads `pyproject.toml`, unpinned), but then run the backend with that venv's Python.
- Nothing from the repos you analyse is ever installed.

### 2. Run

From the repo root, after step 1:

```bash
./run.sh            # development: backend (auto-reload) on :8787 + Vite on :5173
                    # open http://localhost:5173 ; Ctrl+C stops both
./run.sh serve      # one process: builds the frontend, then serves UI + API on
                    # http://127.0.0.1:8787
```

Use `./run.sh serve` for everyday use and `./run.sh` when changing code. On Windows, or to start the pieces by hand:

```bash
# terminal 1 (API, plus the built frontend if frontend/dist exists)
cd backend && uv run python -m app
# terminal 2 (dev UI only, proxies /api to :8787)
cd frontend && npm run dev
# or build the UI once so terminal 1 serves it on :8787
cd frontend && npm run build
```

Then paste a GitHub URL, or choose **Local folder**, and press **Generate**. Optional settings (private repos, ports, data location) are in [Configuration](#configuration-environment-variables-all-optional).

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `uv: command not found` / `run.sh` fails at `uv run` | Install uv (table above) and open a new terminal. |
| `ModuleNotFoundError` (fastapi, tree_sitter, ...) | Step 1 was skipped or run in the wrong folder: `cd backend && uv sync --locked`. |
| `vite: command not found` / `Cannot find module` | `cd frontend && npm ci`. |
| Vite or npm errors about the Node version | Upgrade Node to 20.19+ (`node -v`). |
| Page loads but every request fails (`backend: unreachable`) | The backend is not running, or something else uses port 8787. Set `DIAGRAMMA_PORT` (and the Vite proxy in `frontend/vite.config.ts`) if you must change it. |
| `:8787` shows a JSON "not found" instead of the app | `frontend/dist` is missing: run `./run.sh serve` or `npm run build` in `frontend/`. |
| `CLONE_FAILED` / `AUTH_REQUIRED` for a GitHub repo | `git` is missing, offline, or the repo is private: set `GITHUB_TOKEN`. |
| `Permission denied: ./run.sh` | `chmod +x run.sh`. |

## Scope

**In (MVP):** whole-app C4 Component diagram (containers → components → externals/data stores), TS/JS and Python analysis, C4 and flowchart output, editable code pane with live preview, SQLite history, copy `.mmd`.

**Also built (M8, SPEC §9.3):** a **Dependencies** tab: a layered graph built from import statements (foundations at the bottom, entry points on top, import cycles reported instead of hidden, redundant and very long edges left out and counted).

**Out:** persons/actors, class-level detail, runtime analysis, multi-user/auth/hosting, LLM features. Later work is in SPEC.md §12.

Repos are assumed to be your own or trusted ones. Analysis is **static only**: repo code is never executed and its dependencies are never installed.

## Architecture

```
Browser (React + TS + Vite)  ──HTTP/JSON + SSE──►  FastAPI backend (127.0.0.1:8787)
  form · history · split view                        job runner ─► analysis pipeline ─► Mermaid renderers
  CodeMirror · Mermaid · pan/zoom                    SQLite (history) · clone cache (~/.cache/diagramma/repos)
```

- Mermaid is rendered **in the browser**; the backend produces Mermaid *text* plus the intermediate model.
- Dev: backend on `127.0.0.1:8787`, Vite on `5173` proxying `/api`.
- Run mode: FastAPI serves the built frontend, so one command starts everything.

### Analysis pipeline

```
URL ─► Fetch ─► Scan ─► Detect ─► Model ─► Render ─► { c4, flowchart }
       clone    files   containers, graph   Mermaid
                        components,         text
                        relations,
                        externals
```

Stages communicate **only through the Pydantic model** so each can be tested alone, and each emits an SSE progress event (Cloning → Scanning → Detecting → Rendering).

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic v2, `sse-starlette` |
| Analysis | system `git` (shallow fetch), `tree-sitter` + `tree-sitter-language-pack`, `PyYAML` |
| Storage | SQLite via the standard-library `sqlite3` |
| Tooling | `uv`, `pytest`, `ruff` |
| Frontend | React 18, TypeScript (strict), Vite, Tailwind, TanStack Query |
| UI libs | `mermaid` (pinned, `securityLevel: "strict"`), `react-zoom-pan-pinch`, `@uiw/react-codemirror` + `codemirror-lang-mermaid`; the split view is a small custom component (SPEC §4.3) |
| Contract | TS types generated from FastAPI's OpenAPI via `openapi-typescript` |
| Frontend tests | Vitest + React Testing Library |

## Project layout

```
diagramma/
  backend/
    pyproject.toml, uv.lock
    scripts/dump_openapi.py   # schema for `npm run gen:api` (no server needed)
    app/
      __main__.py             # `python -m app`: loopback-only server
      main.py                 # app factory, error handlers, CORS, static frontend mount
      api/routes.py           # all /api routes (incl. SSE)
      jobs/                   # manager.py (registry + process pool), pipeline.py (worker)
      db.py                   # SQLite DiagramStore
      errors.py, models.py    # error codes; Pydantic model + API schemas
      analysis/               # fetch, scan, manifests, containers, externals (+catalogue.yaml),
                              # components, parse (tree-sitter), graph, relations, reduce, build
      render/                 # c4.py, flowchart.py, escape.py
    tests/                    # pytest; sample repos are built on the fly (helpers.py),
                              # golden/ holds the expected Mermaid output
  frontend/
    src/
      App.tsx
      api/                    # generated schema.d.ts, client, SSE hook, editor state hook
      hooks/                  # useDebounced, useMediaQuery / useSystemDark
      components/             # RepoForm, ProgressPanel, HistoryList, DiagramWorkspace,
                              # SplitLayout, CodePane, StatusBar, DiagramPane, MermaidView
  SPEC.md  README.md  progress.md
```

## API

All routes under `/api`, bound to `127.0.0.1`.

| Method & path | Purpose |
|---|---|
| `POST /api/diagrams` | `{ url, ref? }` **or** `{ path }` (absolute folder path, analysed in place; reuse is decided by a content fingerprint after the job) → `{ jobId }`, or `{ diagramId }` if repo+ref+commit already exists (checked with `git ls-remote`, no clone) |
| `GET /api/jobs/{jobId}/events` | SSE: `stage {stage, message}`…, then `done {diagramId, …summary}` or `error {code, message}` |
| `GET /api/diagrams` | History summaries, newest first |
| `GET /api/diagrams/{id}` | Full record: texts at the default depth, depth range, model, metadata, warnings, which views have saved edits |
| `GET /api/diagrams/{id}/views/{format}/{depth}` | One rendering (`format` = `c4` \| `flowchart` \| `layers`, `depth` 1…max): generated text, saved edit, boxes/edges/hubs drawn, and for `layers` a summary of the layering |
| `PUT /api/diagrams/{id}/edits/{format}/{depth}` | Save edited text for that view (any format); `DELETE` discards the edit. Both return the view |
| `DELETE /api/diagrams/{id}` | Remove from history |
| `GET /api/diagrams/{id}/nodes/{nodeId}?depth=` | Details of one box (click it in the UI): kind, paths, evidence, contents, hub flag, `uses` / `used_by` lists |
| `GET /api/fs/dirs?path=&hidden=` | Folder browser: sub-directories of `path` (default home), parent, repo hint. Names only |
| `GET /api/health` | Liveness + version |

Every error, including unknown routes, has the shape `{ "error": { "code", "message" } }`. Codes: `INVALID_URL`, `INVALID_PATH`, `PATH_NOT_FOUND`, `REPO_NOT_FOUND`, `AUTH_REQUIRED`, `CLONE_FAILED`, `NOTHING_DETECTED`, `TIMEOUT`, `DIAGRAM_NOT_FOUND`, `NODE_NOT_FOUND`, `JOB_NOT_FOUND`, `VALIDATION_ERROR`, `INVALID_DEPTH`, `LAYERS_UNAVAILABLE`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INTERNAL_ERROR`.

## Data model

Pydantic `Model` = `system_name`, `containers[]` (each with a flat `components[]` that forms a tree through `parent`/`depth`), `externals[]`, `relations[]` (between the leaf components), `warnings[]`. Full field definitions: SPEC.md §7. The model is stored as JSON with each diagram and exposed through the API so later features (details panel) need no re-analysis.

SQLite (schema v2, migrated in place from v1; SPEC.md §5.3; file at `$DIAGRAMMA_DATA_DIR/diagramma.db`, default `~/.local/share/diagramma/`; `ref` is `''` when none, `repo_url` is lowercased): a `diagrams` table and an `edits` table keyed by (diagram, format, depth). Generated texts (`mermaid_c4`, `mermaid_flowchart`, rendered at the default depth) are **never modified**; other depths are rendered on demand from the stored model, and user edits live in `edits`. `UNIQUE (repo_url, ref, commit_sha)`.

## Detection rules (MVP summary)

Heuristic and deterministic; every element records `evidence`. Details in SPEC.md §8.

- **Containers:** docker-compose services → workspace packages / sub-folders with their own manifest → single container named after the repo. Kind from dependencies (web framework → `api`, React/Vue/… → `webapp`, bin → `cli`, no entrypoint → `library`).
- **Components:** a tree per container: folders nested up to 6 levels (pass-through folders merged), and for containers up to 300 source files, one component per file at the bottom. Roles from folder names (inherited by sub-folders and files); root-level files → "Core". Exclude tests, fixtures, mocks, docs, build output, generated code.
- **Relations:** tree-sitter imports → file graph → edges between leaf components. Rendering rolls them up to the chosen depth (counts add up); labels come from the role pair.
- **Externals / data stores:** built-in catalogue matched on dependencies, compose images and env var names.
- **Readability:** top-level components are capped at 60 (smallest merge into "Other <container>"); the default depth is the deepest level that shows at most 60 boxes; the flowchart groups cross-group edges and marks hubs (SPEC §9.2).
- Unsupported languages fall back to directory + manifest detection with a warning.

## Mermaid output

Both dialects come from the same model: a `flowchart` (the default view: nested groups, role colours, edge thickness, hubs) and native `C4Component` (best at low depth). The default depth is stored; any other depth is rendered on demand. Requirements:

- **Deterministic:** stable ordering, so the same commit + tool version yields byte-identical text.
- IDs sanitised to `[A-Za-z0-9_]`, labels escaped, header comment with repo, ref, depth, SHA, commit date, tool version.
- No `Person` elements.

## Frontend behaviour (key points)

- Split: code 33% / diagram 67%, draggable divider, double-click resets (arrow keys also resize). Panes fold to a rail (code-only / diagram-only; Alt+1 / Alt+2); the last open pane can't fold. Layout persisted in `localStorage`. Stacks vertically below ~900 px.
- Editor: live preview debounced ~400 ms; invalid text keeps the last good render and shows the error in a status bar. Save persists to history; Reset restores the generated text. Each format keeps its own edits.
- The diagram pane header holds the Flowchart/C4 toggle (Flowchart by default); a **Depth** control sits above the split. Each (format, depth) view has its own text, draft and saved edit. The diagram has pan/zoom and Fit; it is always drawn on a light canvas; a failed C4 render offers the flowchart.
- Copy acts on the *current editor text*, including unsaved edits.
- Re-generating a repo never silently overwrites saved edits.

## Safety (trusted repos only)

Accept only `https://github.com/...` URLs in `url` (local folders come only through `path`; the folder is read in place and never modified, `.gitignore` is honoured in git repos, any readable folder is allowed because the API is loopback-only); static analysis only; bind to `127.0.0.1` with CORS limited to the local frontend origin; escape text going into Mermaid; optional `GITHUB_TOKEN` from the backend environment, never logged or returned.

## Development

Install and run: see [Getting started](#getting-started). Day-to-day commands:

```bash
# backend (from backend/)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload   # what ./run.sh runs
uv run pytest
uv run ruff check . && uv run ruff format .

# frontend (from frontend/)
npm test
npm run gen:api                # regenerate TS types from the OpenAPI schema (no server needed)
npm run build                  # type-checks (tsc, strict) and builds to frontend/dist
```

### Configuration (environment variables, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `GITHUB_TOKEN` | unset | Read access for private repos. Passed to git via env config; never logged or returned. |
| `DIAGRAMMA_DATA_DIR` | `~/.local/share/diagramma` | Where `diagramma.db` (history and saved edits) lives. |
| `DIAGRAMMA_CACHE_DIR` | `~/.cache/diagramma` | Shallow clones (`repos/`). Safe to delete. |
| `DIAGRAMMA_PORT` | `8787` | Port for `python -m app` (the host is always `127.0.0.1`). |
| `DIAGRAMMA_FRONTEND_DIST` | `frontend/dist` | Built frontend to serve. |
| `DIAGRAMMA_FRONTEND_ORIGIN` | `http://localhost:5173` | The one browser origin allowed by CORS (besides `127.0.0.1:5173`). |

## Known limits

- The Dependencies tab is whole-system and uses import statements only (TS/JS and Python). Import cycles are shown as an upward-dependency count and a top-10 list, not drawn. There are no layer bands, no hub marking and no per-container filter yet. Diagrams generated by an earlier version must be submitted again before this tab works for them.
- Very coupled codebases stay busy: at the default depth Django still draws ~130 edges (after grouping and hub handling). Pick a lower depth for an overview. Hub edges are not drawn in the flowchart (the C4 tab draws every edge), and there is no per-component details panel yet, so you cannot list exactly who depends on a hub.
- Containers above 300 source files stop at folder level (no per-file components); components are limited to 6 levels.
- Only TypeScript/JavaScript and Python are analysed in depth. Other languages get folders and manifests only, with a warning.
- TS/JS imports resolve relative paths, `index` files, `.js`→`.ts`, and the `@/`, `~/`, `#/` aliases. `tsconfig` `paths`/`baseUrl` and package `exports` maps are not read.
- Dynamic dependencies (DI, reflection, runtime URLs) are invisible. Frontend→backend HTTP calls are only drawn when docker-compose `depends_on` says so.
- Edges backed only by compose, manifests or env vars (no import evidence) are attached to a representative component and are weaker evidence.
- Unsaved editor drafts are not stored: switching to another history entry discards them. Saved edits persist.
- A job that times out (10 min) is reported as an error, but its worker process is not killed.
- The diagram always renders on a light canvas (Mermaid's dark C4 theme is unreadable).

## Implementation conventions

- Follow the milestone order (M1, M2, …) in SPEC.md §11 and tick items off in [progress.md](progress.md); record every deviation there and in SPEC.md.
- Keep stages pure and model-driven; no stage reads another stage's internals.
- Every detection rule has a test that builds a small sample repo (`backend/tests/helpers.py`); renderers have golden-file tests (`backend/tests/golden/`) that also cover determinism, and the frontend checks that the golden output parses with the pinned Mermaid.
- Tests never touch the real history database or clone cache (an autouse fixture redirects both).
- Regenerate the TS API types whenever backend schemas change; never hand-edit `schema.d.ts`.
- Don't pull in roadmap features (SPEC.md §12) without updating the spec first.

## Acceptance

The MVP is done when all items in SPEC.md §11 (1–8, including 4a–4c) pass. [progress.md](progress.md) mirrors them as a checklist.
