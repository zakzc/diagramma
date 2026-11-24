# Progress

Tracks implementation of the MVP described in [SPEC.md](SPEC.md) / [README.md](README.md).

Milestones are named **M1, M2, …** (as in SPEC §11).

**Legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (add a reason)

**Current milestone:** none open. M7 (deeper components) and M8 (Dependency graph view, simpler form) are built on branch `deeper-components`; M7 is committed locally, M8 is ready to commit; neither is pushed. M1-M6 are in PR #1. M10 (local folder input) and **M11 (details panel, SPEC §9.5)** are built on branch `deeper-components`, committed locally, not pushed. Roadmap (SPEC §12) otherwise not started.
**Last updated:** 2026-11-24

---

## M1 — Skeleton
- [x] Repo scaffolding: `backend/` (uv, pyproject, ruff, pytest) and `frontend/` (Vite, React 18, TS strict, Tailwind)
- [x] FastAPI app with `GET /api/health` (liveness + version)
- [x] Vite dev proxy `/api` → `127.0.0.1:8787`
- [x] Pydantic models in `models.py` (SPEC §7)
- [x] OpenAPI → TS type generation (`npm run gen:api`)
- [~] Frontend renders a hard-coded Mermaid C4 diagram (`securityLevel: "strict"`, raised limits)
- [x] FastAPI serves built frontend (run mode)

## M2 — Fetch & scan
- [x] URL validation (`https://github.com/...` and `owner/repo`), `INVALID_URL`
- [x] `git clone --depth 1` into `~/.cache/diagramma/repos/`, optional ref, optional `GITHUB_TOKEN`
- [x] Error mapping: `REPO_NOT_FOUND`, `AUTH_REQUIRED`, `CLONE_FAILED`
- [x] File scanner with ignore rules (tests, fixtures, mocks, docs, build output, generated)
- [x] Job registry + `ProcessPoolExecutor`, one job per repo, 10-min timeout
- [x] `POST /api/diagrams` and `GET /api/jobs/{id}/events` (SSE)
- [x] Frontend: RepoForm, ProgressPanel, SSE hook, readable errors

## M3 — Containers & externals
- [x] docker-compose service detection
- [x] Workspace / sub-manifest detection (`package.json`, `pnpm-workspace.yaml`, `pyproject.toml`, `requirements.txt`)
- [x] Container kind classification; single-container fallback
- [x] Externals catalogue (`catalogue.yaml`) matched on deps, compose images, env vars
- [x] Container-level C4 renderer
- [x] End to end: input → render → copy `.mmd`
- [-] `GET /api/diagrams/{id}/download` (removed after M3: copy replaces download)

## M4 — Components & relations
- [x] Component detection by folder convention + role mapping; "Core" grouping
- [x] tree-sitter import extraction: TS/JS
- [x] tree-sitter import extraction: Python
- [x] File graph → component edges → container edges (+ compose `depends_on`)
- [x] Edge collapsing and role-pair labels
- [x] `reduce.py`: cap at 60 components, "Other <container>" merge + warning
- [x] `render/c4.py` (full) with header comment and ID/label escaping
- [x] `render/flowchart.py` (subgraphs, classDef colours, cylinders)
- [x] Unsupported-language fallback with warning
- [x] Golden-file tests incl. determinism (byte-identical output)

## M5 — History
- [x] SQLite schema + `db.py` (SPEC §5.3)
- [x] Reuse entry for same repo + ref + commit
- [x] `GET /api/diagrams`, `GET /api/diagrams/{id}`, `DELETE /api/diagrams/{id}`
- [x] Frontend HistoryList: reopen, delete, foldable sidebar

## M6 — Editor split view
(Can start right after M1; only needs text.)
- [x] SplitLayout (custom, not `react-resizable-panels`, see decisions): 1/3 : 2/3 default, drag, double-click reset
- [x] Fold states: split / code-only / diagram-only; last pane can't fold
- [x] Persist layout in `localStorage`; stack vertically below ~900 px
- [x] CodePane (CodeMirror 6, line numbers, Mermaid highlighting or plain)
- [x] Live preview (~400 ms debounce), keep last good render on error
- [x] StatusBar with error + line number, dirty marker
- [x] DiagramPane: pan/zoom, fit-to-screen, C4/Flowchart toggle, flowchart offer on C4 failure
- [x] Per-format edits; Reset
- [x] `PUT` / `DELETE /api/diagrams/{id}/edits/{format}` + Save
- [x] Copy .mmd uses current editor text
- [x] Light/dark follows system theme

## M7 — Deeper components and a clearer view
Requested after the MVP: components were only one level deep and dense diagrams were unreadable.
- [x] Components as a tree (folders nested to 6 levels, pass-through folders merged, files as leaves for containers up to 300 files)
- [x] Role inheritance down the tree; empty `__init__.py` files mapped (not drawn) so import edges survive
- [x] One import statement = one dependency (no double count for `from pkg import submodule`)
- [x] Depth roll-up (`render/view.py`): relations stored between leaves, re-pointed to any depth; auto depth = deepest level with at most 60 boxes
- [x] Nested flowchart (subgraphs, role colours, edge thickness and `×N`, no "Uses" label), nested `Boundary` in C4
- [x] Grouped edges: edges crossing a group attach to the sibling groups; hubs (>= 8 dependents and >= 25% of dependents) drawn once with "used by N"
- [x] Top-level cap (60) now merges subtrees; schema v2 (edits table keyed by format and depth, depth range columns) with an in-place v1 migration
- [x] API: `GET …/views/{format}/{depth}`, `PUT`/`DELETE …/edits/{format}/{depth}`, `INVALID_DEPTH`
- [x] UI: Depth control, per-view drafts and edits, size/hub note, large-view warning, Flowchart as default tab
- [x] Verified in a real browser on fastapi template, flask, typer and Django (all depths, edits scoped per depth across a reload)

## M9 — Imports view (React file graph)
Specified in SPEC §9.4. A file-level import diagram for React apps (JS/TS), colour- and shape-coded by file kind.
- [x] `analysis/filekind.py`: classifier (entry, page, state, hook, component, types, db, api, config, util) from path, name and content; `parse.read_js_file` adds JSX detection from the tree-sitter tree
- [x] `analysis/files.py`: `Model.files` / `Model.file_imports`, only for containers that declare or import React; reuses the existing import resolution (relative, alias, `index`); tool version 0.4.0
- [x] `render/imports.py`: `flowchart LR`, one subgraph per top-level folder, shapes and colours per kind, API-client packages and catalogue services/databases as external boxes, hubs drawn once ("used by N"), `×N` and thickness; colours come from the `legend` in the summary
- [x] API: `imports` format (always depth 1) with an `imports` summary; `409 IMPORTS_UNAVAILABLE` for non-React repos and diagrams from before this version
- [x] UI: an "Imports" tab, colour legend strip with counts and what was left out, Depth control hidden on this tab, one edit per diagram regardless of the depth chosen elsewhere
- [x] Tests: classifier per kind, hubs, escaping, determinism, non-React and mixed monorepo, golden file also parsed by the pinned Mermaid; checked on this repo's own frontend
- [-] Not built: tsconfig `paths`/`baseUrl` aliases (as in M4), per-folder collapsing for very large apps, Vue/Svelte/Angular

## M8 — Dependency graph view (layered)
Specified in SPEC §9.3. **Built in a simpler form** (plain top-down layout; see the `[-]` items for what was deferred). A layered graph built from import statements: foundations at the bottom, entry points on top, cycles reported instead of hidden.
- [x] Relation provenance: an `evidence` set on every relation (`import`, `compose`, `manifest`, `env`), unioned through the depth roll-up, grouping and the top-level cap merge (no change for existing views)
- [x] `analysis/layering.py` (pure functions): import-only graph at a depth (boxes plus externals that an import references); isolated components counted, not drawn
- [x] Cycle breaking with the weighted Eades-Lin-Smyth ordering; upward edges reported, large cycles never collapsed
- [x] Layering by longest path over forward edges; externals in layer 0
- [x] Transitive reduction and long-edge omission (`MAX_SPAN` = 3, kept after checking four repos), all counted
- [x] Property tests on 25 random graphs plus targeted cases: forward edges strictly decrease the layer, no edge lost or double counted, reduction preserves reachability, deterministic under input shuffling
- [x] `render/layers.py`: plain top-down `flowchart TB`, layer number and colour per layer, container name when there are several, `×N`/thickness, cylinders for externals, red dashed "↑N" boxes; golden files and a parse test with the pinned Mermaid
- [x] API: `layers` in the views and edits endpoints with a `layers` summary; `409 LAYERS_UNAVAILABLE` for diagrams from before provenance; schema v3 and an in-place v2→v3 migration (tested, and checked on a real database)
- [x] UI: a "Dependencies" tab, summary strip with what was left out, list of the strongest upward dependencies; a view that fails to load keeps the previous one on screen read-only; workspace tests
- [x] Verified in a real browser on the FastAPI template, Flask, Django (and the upgrade of an old diagram); exported texts render in Mermaid 11.17.2; Django default view computed in 20 ms
- [-] Layer bands (a subgraph per layer, "Layer N" titles): deferred, draws much taller (Django depth 1 about 3,500px). Plain ranking plus layer numbers and colours does the job
- [-] Hub marking in this view: deferred, the reduction already removes most hub edges in the prototype
- [-] Per-container filtering and a toggle to draw upward edges: deferred (SPEC §12)

## M10 — Local folder input (SPEC §5.6)
Requested after M9: diagram a repository from a folder on the machine, not only from GitHub. **Built.**
- [x] Decisions 1-6 recorded in SPEC §5.6 (fingerprint, honour `.gitignore`, folder-name label + full path, `source` field, folder browser, any folder)
- [x] Open questions 7-9 were not answered; built with defaults (no `.gitignore` handling without `.git`; browser starts at home with a Hidden toggle; symlinked folders selectable)
- [x] Backend: `RepoSpec.path`; "open local folder" step returning the same `ClonedRepo` as `clone_repo`; path validation (absolute, exists, directory, resolved)
- [x] Content fingerprint as `commit_sha`; `.gitignore` honoured (`git ls-files --cached --others --exclude-standard` in a git repo); `repo_url` = `file://<path>`, `owner` = `local`, `name` = folder name; reuse on unchanged folder
- [x] `POST /api/diagrams` body `{ url, ref? }` or `{ path }` (exactly one); `INVALID_PATH` (400) and `PATH_NOT_FOUND` (404) in `errors.py`; job key by resolved path
- [x] Pipeline stage message "Reading <folder>"; header comment without date for local diagrams (determinism)
- [x] `source` (`github` | `local`) on `DiagramRecord`/`DiagramSummary`; `diagrams.source` column, schema v4 with in-place migration (existing rows `github`); `__version__` 0.5.0
- [x] `GET /api/fs/dirs?path=`: sub-directories only, parent, repo hint; `INVALID_PATH` / `PATH_NOT_FOUND`
- [x] Frontend: form mode switch (GitHub URL | Local folder), folder browser + path field, hide ref; history entry shows folder name, tooltip and header line show the full path; `npm run gen:api`
- [-] New test files: not added (user's standing rule: they test it themselves). Checked by hand instead: path errors, folder not modified (tree compared before/after), `.gitignore` honoured, reuse through the API (one history entry after two submits), `file://` still rejected in `url`. Existing DB tests updated for schema v4 and `source`
- [x] Update README (input modes, folder browser, error codes)

## M11 — Details panel (SPEC §9.5)
Roadmap item 1, promoted after M10. **Built.**
- [x] Spec: SPEC v0.12 (§9.5, API row, milestone, acceptance 21-23, roadmap item 1 updated); open questions 1-3 with defaults
- [x] `analysis/details.py::node_details`: components (relations at the box's own level via `build_view(model, k.depth)`, hub flag from `drawn_relations` at the viewed depth), containers (relations rolled up per container), external systems, React files (`file_imports`)
- [x] `GET /api/diagrams/{id}/nodes/{nodeId}?depth=`; `NodeDetails` / `NodeLink` models; `NODE_NOT_FOUND` (404); `INVALID_DEPTH` reused
- [x] Frontend: click on a box (flowchart nodes and clusters, C4 elements) with a drag guard; `DetailsPanel` overlay with clickable Uses / Used by; closes on view change; `npm run gen:api`
- [x] Verified in a real browser (Brave via puppeteer-core, on this repo analysed as a local folder): panel opens in Flowchart, C4, Dependencies and Imports; a cluster click works; a link inside the panel selects the other box; a drag does not open it. Found and fixed: Mermaid prefixes box ids with `mmd-N-`, so the first id parser matched nothing
- [-] New test files: not added (standing rule). Existing 223 backend and 84 frontend tests still pass
- [-] Layer number / upward edges per box, selection highlight: deferred (SPEC §9.5 open questions 1-2)

## Cross-cutting
- [x] Unified error shape `{ "error": { code, message } }`
- [x] CORS limited to local frontend origin; bind `127.0.0.1`
- [x] Backend sample repos + pytest coverage per detection rule (94% line coverage; the rest is mostly defensive branches)
- [x] Frontend Vitest/RTL tests (split layout, editor, history)
- [x] README dev commands verified against reality

## Acceptance (SPEC §11)  (all met; 15-20 are M10, 21-23 are M11)
- [x] 1. URL → progress → rendered whole-app diagram
- [x] 2. Containers as boundaries with components; distinct DB/external symbols; cross-container relations; no persons
- [x] 3. Copied `.mmd` text renders in an external Mermaid viewer (checked with Mermaid 11.17.2 in a bare page, not a hosted viewer; the app pins 12.3.0)
- [x] 4. C4/Flowchart toggle; failed C4 offers flowchart
- [x] 4a. Opens at ~1/3 : 2/3 with draggable divider
- [x] 4b. Panes fold; last open pane can't fold; layout persists
- [x] 4c. Live edit; invalid text keeps previous render + error; Save persists across restart; Reset restores
- [x] 5. History persists across restarts, reopens instantly
- [x] 6. Re-submitting an unchanged repo reuses the entry
- [x] 7. Same commit + version → byte-identical Mermaid
- [x] 8. Unsupported-language repo yields coarser valid diagram + warning
- [x] 9. (M7) Components nest; Depth control; default depth draws at most 60 boxes; edits are per (format, depth) and survive a reload without leaking
- [x] 10. (M7) Dense code stays readable: grouped edges, hubs drawn once with "used by N", header says how many
- [x] 11. (M8) Dependencies tab shows a layered graph: layer numbers, every drawn forward edge goes from a higher to a lower layer, externals in layer 0
- [x] 12. (M8) Cyclic code still layers (Flask, Django): large cycles are never collapsed; the upward-edge count and the 10 strongest are shown
- [x] 13. (M8) Only import-derived edges are used; compose/manifest/env-only edges never appear
- [x] 14. (M8) Readable and honest by default: no drawn forward edge spans more than `MAX_SPAN` layers; the summary states what was omitted; deterministic; parses in two Mermaid versions; Django default view computed in under 1 s
- [x] 15. (M10) A local folder path gives the same views, depth control, edits and history as a GitHub repo, with no network
- [x] 16. (M10) The folder is not modified
- [x] 17. (M10) Relative path, file, missing path, both/neither of `url` and `path` are refused with a readable error
- [x] 18. (M10) Unchanged folder reuses its entry; a changed one makes a new entry; byte-identical text for same content and version
- [x] 19. (M10) GitHub input unchanged; `file://` still rejected in `url`
- [x] 21. (M11) Clicking a box opens the panel in all four tabs; a drag does not
- [x] 22. (M11) Uses / Used by list every dependency at the box's own level, hub edges included; names are clickable
- [x] 23. (M11) Unknown id, non-model box or bad depth: readable message, nothing breaks
- [x] 20. (M10) Folder browser lists directories only and reaches any readable folder; `.gitignore` honoured; local entry shows folder name and full path; schema v4 migration

---

## Log

| Date | Note |
|---|---|
| 2026-11-24 | M11 built: details panel (SPEC v0.12 §9.5), `GET /api/diagrams/{id}/nodes/{nodeId}`, `DetailsPanel`. Checked in Brave on this repo analysed as a local folder (all four tabs, cluster click, link navigation, drag guard). |
| 2026-11-24 | M10 built: local folder input (`path`), fingerprint identity, `.gitignore` via `git ls-files`, `source` field (schema v4, tool 0.5.0), `GET /api/fs/dirs` folder browser, form mode switch, history label. 223 backend and 84 frontend tests pass; checked end to end against a running server on a temp git repo. |
| 2026-11-24 | Docs: **M10 (local folder input) specified** in SPEC v0.11 (§5.6, API, safety, milestones, acceptance 15-19, risks); roadmap item 9 moved into the build. Open questions 1-6 answered by the user and folded into the spec (folder browser, `source` field, schema v4, `.gitignore`); questions 7-9 remain. No code changed. |
| 2026-11-19 | M8 built (simpler form): provenance, layering, Dependencies tab, schema v3. 215 backend and 80 frontend tests pass. Verified in a real browser (FastAPI template, Flask, Django, upgrade of an old diagram), in Mermaid 11.17.2, Django view in 20 ms. |
| 2026-11-19 | Docs: milestones renamed M1…M7; **M8 (Dependency graph view) specified** in SPEC v0.8 (§9.3, API, model, acceptance 11-14, risks) and planned here with a build-order checklist. Design checked with a throwaway prototype on four real repos (not committed). No code changed. |
| 2026-11-19 | M7 (branch `deeper-components`): nested components, depth control, grouped edges, hubs, per-depth edits, schema v2 with migration. 152 backend and 71 frontend tests pass; verified in a real browser on four repos. |
| 2026-11-19 | Final pass: error envelope everywhere, CORS and loopback-bind tests, `python -m app`, README commands verified clean, README/SPEC corrected, acceptance 3 checked with a second Mermaid version, 24 extra backend tests. 102 backend and 59 frontend tests pass. |
| 2026-11-19 | M6 done: edit endpoints, split view with folds, resize and persistence, CodeMirror pane, live preview with error bar, Save/Reset, per-format edits, pan/zoom + Fit, system theme, narrow-screen stacking. Verified end to end in a real browser. 74 backend and 59 frontend tests pass. |
| 2026-11-19 | M5 done: SQLite store, list/get/delete endpoints, reuse by repo+ref+commit via `ls-remote`, history sidebar with reopen, delete and fold. Download replaced by Copy. Verified live: generate, restart, history persists, case-insensitive re-submit reuses the entry in 0.85s, delete. 70 backend and 29 frontend tests pass. |
| 2026-11-19 | M4 done: component detection, tree-sitter import graph (TS/JS, Python), component and container relations with role-pair labels, 60-component cap, `C4Component` and flowchart renderers with golden tests, flowchart toggle. Verified on `fastapi/full-stack-fastapi-template`, `tiangolo/typer`, `pallets/flask`, `django/django` (8s, 16 components). 55 backend and 21 frontend tests pass; both golden diagrams parse with the pinned mermaid. |
| 2026-11-19 | M3 done: compose/workspace/manifest container detection, catalogue-based externals, container relations, `C4Container` renderer with golden test, in-memory store, diagram/download endpoints, diagram pane with download and copy. Verified on real repos (`fastapi/full-stack-fastapi-template`, `tiangolo/typer`). 42 backend and 18 frontend tests pass; the golden output parses with the pinned mermaid. |
| 2026-11-19 | M2 done: URL validation, git fetch with cache, scanner, job manager (spawn process pool) with SSE, form and progress UI. Verified against real GitHub (`octocat/Hello-World` -> NOTHING_DETECTED, missing repo -> error). 31 backend and 16 frontend tests pass. |
| 2026-11-19 | M1 scaffolded: backend health + tests, Vite/React/Tailwind app, generated API types, run mode serves `dist`. Mermaid render not yet checked in a real browser. |
| 2026-11-19 | SPEC v0.4 written; README and progress tracker added. No code yet. |

## Decisions & open questions

- M10 (planning): **the folder is read in place, and a content fingerprint replaces the commit as identity.** A local folder may have uncommitted changes or no git at all, so a commit SHA cannot say what was analysed. The fingerprint (sorted relative path + size + mtime of scanned files) keeps reuse (acceptance 6) and determinism (acceptance 7). Cost: touching a file makes a new history entry.
- M10: **`path` is a separate field, not a `file://` URL in `url`.** This keeps the GitHub-only check in §5.5 intact and makes the two inputs impossible to confuse.
- M10: browsers cannot give a real folder path, so the UI takes a typed/pasted path. A server-side folder browser is out of scope for now.
- M10 decisions (2026-11-24): 1 content fingerprint; 2 honour `.gitignore`; 3 folder name as label with the full path as tooltip and header line (the user said "whichever lets me see the full code", so the full path is always visible; revisit if wanted); 4 `source` field, schema v4, tool 0.5.0; 5 folder browser (new `GET /api/fs/dirs`, directory names only); 6 any folder.
- M10 open questions (SPEC §5.6): 7 `.gitignore` without git (`pathspec` dependency, own matcher, or skip); 8 browser start folder and hidden folders; 9 symlinked folders in the browser.

- M8 (built): **simpler approach.** Plain top-down `flowchart TB`, layer number and colour on each box. Not built: layer bands, hub marking, drawing upward edges, per-container filtering (roadmap). Real results match the prototype: Django at package level 10 layers and 34 upward edges (114 edges become 19 drawn), Flask 14 layers and 25 upward, FastAPI template 10 layers and no cycles (125 become 57).
- M8: the strip tells the user what was left out (implied edges, edges longer than 3 layers, isolated components, upward edges) so nothing is silently dropped. The strongest upward dependencies are the most useful output on cyclic code (Django: `Core → DB ×66`, `Utils → Core ×15`).
- M8: diagrams generated by earlier versions have no relation provenance. Their Dependencies tab answers `409 LAYERS_UNAVAILABLE`: "Submit the repository again". Re-submitting regenerates them (tool version 0.3.0) under the same history entry, keeping saved edits. Other views of old diagrams keep working.
- M8: schema v3 removes the SQL `CHECK` on `edits.format` (the API validates the format). A v1 database from the first release was migrated in place on a real machine (integrity check ok, all diagrams kept), and v2 to v3 is covered by a test.
- M8: found by a test and fixed: when a view failed to load the editor stayed editable and showed another view's text. A failed view now leaves the previous one on screen read-only and the tabs usable (`useDiagramEditor` tracks `stale` separately from `loading`).

- M8 (planning, prototype on real data, nothing in the repo): **cycles are broken by ordering, not collapsed.** Django at package level is a single strongly connected component of 15 of 19 packages, so collapsing would erase its structure. A weighted greedy order gives 10 layers and 34 upward edges of 114.
- M8: **transitive reduction is what makes it readable.** Forward edges after cycle breaking and reduction: FastAPI template (depth 2) 125 to 74, Flask (depth 2) 91 to 45, Django (depth 1) 80 to 22. FastAPI at depth 3 stays high (320 to 236), which is why long edges are also omitted.
- M8: **upward edges are summarised, not drawn, by default.** With Django's 34 red lines over 22 forward ones the layering disappeared. They are shown as "↑N" on their endpoints and listed in the summary. A toggle is on the roadmap.
- M8: **layer bands (a subgraph per layer plus invisible links) work in Mermaid** and give explicit "Layer N" labels; plain `flowchart TB` also ranks correctly but is unlabeled. Bands are the planned default. Risk: tall drawings for repos with many layers (Django depth 1 renders about 3,500px tall). To check in M8.
- M8: relations need **provenance** (`evidence`): today import edges and the weaker compose/manifest/env fallback edges are merged, which would invent layers. This changes the model, so it is the first M8 item.
- M8: the view is named "Dependency graph" in the docs and labelled **Dependencies** on the tab; its format id is `layers`. Open question for M8: whether the default `MAX_SPAN` of 3 is right (tune on the four reference repos).

- M7: the leaf level is **files** for containers up to 300 source files and **folders** above that. Reason: a file-level model of a 3,000-file repo is large and no depth would be readable; folder level keeps Django at 228 components (analysed in 6.5s).
- M7: edges are stored only between leaves. Any depth is computed on demand by rolling them up, so no re-analysis and no extra storage. Only the auto-depth texts are stored; other depths are rendered from `model_json` per request (milliseconds even for Django).
- M7: **Flowchart is now the default tab** (was C4). Seen in a real browser: Mermaid's C4 layout routes edges through boxes once boundaries nest, while the flowchart stays legible. C4 is kept and draws every edge.
- M7: **hub rule** chosen from real data: Django's `conf`/`utils`/`core` have 14-15 of 16 dependents, Flask's `globals` 11, while the FastAPI template and typer have no component above 6. So: at least 8 dependents and at least 25% of all dependents. Hub incoming edges are not drawn in the flowchart (the node says "used by N", the header comment lists hubs, the UI notes it). Databases and other externals are never hubs. This is a deliberate loss of detail: there is no details panel yet to list exactly who uses a hub.
- M7: edges crossing a group boundary attach to the sibling groups below the common parent, and across containers or to externals to the level-1 component. This takes the FastAPI template at depth 3 from 320 edges to 84, and Django at depth 1 from 114 to 46 (with hubs).
- M7: layout direction inside groups is `LR` (was `TB`): measured on the real text, it gives a landscape drawing that fits the pane better (fit scale 0.16 to 0.21).
- M7: the "boxes" count shown to the user counts drawn leaves only (an expanded group is a boundary), and it is the same number `auto_depth` budgets. A test locks these together (they had drifted: typer showed 65 against a cap of 60).
- M7: tool version bumped to 0.2.0, so stored diagrams are regenerated on the next submit (same id, saved edits kept). A v1 database migrates in place; its edits move to the `edits` table at depth 1.
- M7: not done / known limits: no per-component details panel (the model has the data); very coupled code is still busy at depth 2+ (Django: ~130 edges at the default depth); layout direction and hub thresholds are not user-configurable.

- Final pass: every error now uses the `{error:{code,message}}` envelope, including unknown routes (404), wrong methods (405) and unexpected exceptions (500, details not leaked). New codes `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `HTTP_ERROR`. CORS verified: only `localhost:5173` / `127.0.0.1:5173` get headers; other origins get nothing.
- Final pass: added `python -m app` ([\_\_main\_\_.py](backend/app/__main__.py)), which always binds `127.0.0.1` (the host is deliberately not configurable). Stopping it leaves no orphaned worker or manager processes (checked).
- Final pass: README dev commands verified from a clean `npm ci` / `uv sync`, including the Vite dev proxy to the backend. README gained a configuration table and a known-limits section, and its stale parts (status, stack, layout, "fixtures") were corrected. SPEC no longer lists `networkx` (never used).
- Final pass: external-viewer check for acceptance 3 used a different Mermaid version (11.17.2) in a clean page; all six exported diagrams (C4 and flowchart for fastapi template, flask, gorilla/mux) rendered. A hosted viewer was not used.
- Final pass: added tests for git error mapping and token hygiene, manifest variants (poetry, PEP 621, requirements, pnpm, compose forms), container-kind classification, sibling-package import edges, compose fallback edges, container-only rendering, symlinks, and escaping. Backend 102 tests, frontend 59.

- M6: the split view is a custom component ([SplitLayout.tsx](frontend/src/components/SplitLayout.tsx)), not `react-resizable-panels` (SPEC updated to v0.6). Reasons: folded panes must stay mounted so the editor and the render keep their state, and the behaviours (rails, 1/3 reset, persistence, stacking) are unit-testable without a layout engine. Say if you would rather have the library.
- M6: folding uses rails of 2.25rem. Fold state and ratio persist in `localStorage` (`diagramma.split`); corrupt stored values fall back to defaults and the ratio is clamped to 15-85%. Alt+1 / Alt+2 fold the panes and never fold the last one. Below 900px the panes stack (code on top), and the history sidebar starts folded unless the user chose otherwise.
- M6: edit semantics: text shown = unsaved draft > saved edit > generated; each format keeps its own. "Unsaved changes" means differs from what is saved. Save sends `PUT`. Reset restores the generated text: for a draft it is local, for a saved edit it asks first, then calls `DELETE`. Saving text identical to the generated output clears the edit. Unsaved drafts are lost when switching to another history entry (they are not stored).
- M6: live preview waits 400ms after typing; switching tab or diagram renders immediately. A failed render keeps the last good SVG; the error and its line go to the status bar. The "Show flowchart instead" offer only appears when the *generated* C4 fails, not while the user is mid-edit.
- M6: the diagram is always drawn on a light canvas with Mermaid's default theme (the dark C4 theme made container and relation labels unreadable in a real browser). The editor, sidebar and the rest of the UI follow the system theme.
- M6: fit-to-screen runs once per diagram+format (not on every keystroke, so the user's pan/zoom is kept). Mermaid is configured with `useMaxWidth: false` so fit works on natural size. `suppressErrorRendering` stops Mermaid from injecting error SVGs into the page.
- M6: verified in a real browser (Brave, driven by `puppeteer-core` from the scratchpad, not part of the repo): open from history, break the code (error with line, previous render kept), Reset, edit and Save, reload (edit persists), flowchart tab with its own text, folds, divider drag and persistence, stacking at 700px, generating `pallets/flask` and `gorilla/mux` (Go: warning, one container), and re-submitting a known repo with another diagram open. This surfaced the dark-theme label problem and a duplicated "line N" in error text, both fixed.

- M5: copy replaces download (requested after M4). The Download button and `GET /api/diagrams/{id}/download` are removed, along with the `FORMAT_UNAVAILABLE` error code. The button is now "Copy .mmd". SPEC (now v0.5) and README are updated to match.
- M5: SQLite lives at `$DIAGRAMMA_DATA_DIR/diagramma.db` (default `~/.local/share/diagramma/`). The file and schema are created on first use, not on import, and the schema version is stored in `PRAGMA user_version`. One connection per operation; WAL mode when available.
- M5: `ref` is stored as `''` instead of NULL when no ref was given, so `UNIQUE (repo_url, ref, commit_sha)` treats "no ref" as one value. `repo_url` is stored lowercased, since GitHub names are case-insensitive. `owner` and `name` keep the case of the first generation.
- M5: reuse works in two steps. `POST /api/diagrams` calls `git ls-remote` (about 1s) only when the repo+ref already has history, and returns `{diagramId}` when the commit and tool version match. If the commit can't be resolved (for example a short SHA), a normal job runs and the store's upsert still reuses the entry, so a duplicate is never created.
- M5: a stored diagram made by an older tool version is regenerated in place on re-submit (same id). Its saved edits (`edited_*`) are kept, as the spec requires. The edit endpoints themselves arrive in M6.
- M5: the hard-coded sample diagram from M1 is removed. The empty state is a hint text. History is a foldable sidebar (fold state in `localStorage`), and deleting asks for inline confirmation.
- M5: test isolation. An autouse fixture points `DIAGRAMMA_DATA_DIR` and the clone cache at a temp dir, so tests never touch real history.

- M4: components are one per top-level folder of the *source root* (`src/`, `app/`, `lib/`, else a single top-level Python package, descending through a lone wrapper package such as `src/pkg/`). Root-level files and files outside the source root form "Core". If a real `core/` folder exists, the synthetic one is named "Main". A Core made only of `__init__.py` is dropped.
- M4: acronym folders are upper-cased in names ("API", "DB", "UI"). In a `webapp`, `api/` is a gateway (client code) and `views/` is UI. Elsewhere `views/` is a controller.
- M4: import resolution covers relative paths, `.js` to `.ts` mapping, `index` files, `require()`, dynamic `import()`, re-exports, and the `@/`, `~/`, `#/` aliases (to `src/`, then the container root). Not covered: `tsconfig` `paths`/`baseUrl`, package `exports` maps. Python covers absolute, relative, from-import of submodules, and import roots at the container path and its `src/`.
- M4: a bare import of a workspace sibling's package name draws an edge to the sibling's "Core" component, since there is no deeper evidence about which component it hits.
- M4: external systems are also created from import evidence (hoisted or undeclared dependencies), not just manifests. Container-level evidence (compose `depends_on`, manifests, env vars) is kept as a fallback and attached to a representative component (for example a database goes to the repository component) only when no import evidence already covers that container/external pair. Such edges are weaker evidence than imports.
- M4: a container with no source files (an infrastructure-only compose service) is drawn as a plain `Container(...)` next to the boundaries. Compose services that are external images, such as nginx, point nowhere.
- M4: the 60-component cap (`reduce.py`) merges the smallest components of the busiest container into "Other <container>", remaps relations, and adds a warning. If every container is already down to one component it warns instead.
- M4: all ids (containers, components, externals) share one namespace so Mermaid ids cannot collide.
- M4: the pipeline stores `mermaid_flowchart` too. The diagram pane has a minimal C4/Flowchart toggle and a "Show flowchart instead" offer when C4 fails to render. The full split view and editing stay in M6.

- M3: no persistence yet. `app/store.py` is an in-memory `DiagramStore` with the interface M5 will back with SQLite. The pipeline returns the record to the API process, which stores it, so `done` carries a real `diagramId` and `GET /api/diagrams/{id}` plus `/download` work now. Diagrams are lost on restart until M5.
- M3: with no components yet, `render_c4` emits a `C4Container` diagram (Container / ContainerDb / ContainerQueue / System_Ext). M4 switches to `C4Component` with `Container_Boundary` once components exist. `mermaid_flowchart` is null until M4 (download returns `FORMAT_UNAVAILABLE`).
- M3: the header comment uses the commit date, not the current time, so output stays byte-identical for the same commit and version (SPEC §9.1 says "date"; acceptance 7 needs determinism).
- M3: `Container` gained an `evidence` field (not in SPEC §7), so containers keep evidence like every other element.
- M3: docker-compose `build` with `context: .` and `dockerfile: sub/Dockerfile` maps the service to `sub/` only if that folder has a manifest or source. Otherwise the context is kept.
- M3: example env files (`.env.example`, `.env.sample`, `.env.template`, `.env.dist`) are read for external detection. Real `.env` files are never read.
- M3: relations from external compose services to containers (for example a proxy to the web app) are not drawn. Only containers pointing at externals are.
- M3: `npm run gen:api` now dumps the schema with `backend/scripts/dump_openapi.py`, so no running server is needed. Response models mark defaulted fields as required so the TS types are not all optional.

- M2: the pipeline ends after the scan. The `done` event carries a scan summary with `diagramId: null` until M5 adds persistence.
- M2: clones use `git init` + `fetch --depth 1 origin <ref|HEAD>` + detached checkout, which handles branches, tags and SHAs the same way and refreshes cached clones. The token goes to git via `GIT_CONFIG_*` env vars (an `http.extraheader`), so it never appears in argv or the remote URL.
- M2: GitHub answers "private" and "does not exist" the same way to anonymous clients, so a missing repo without `GITHUB_TOKEN` reports `AUTH_REQUIRED` ("not found or private"). With a token it reports `REPO_NOT_FOUND`.
- M2: a timed-out job is reported as an error (`TIMEOUT`), but its worker process is not killed (a `ProcessPoolExecutor` limitation). The git timeout of 300s bounds the clone itself.
- M2: added error codes `JOB_NOT_FOUND`, `VALIDATION_ERROR`, `TIMEOUT` and `INTERNAL_ERROR` to the SPEC §5.2 list.

- Backend pinned to Python 3.12 via `backend/.python-version` (the system Python is 3.14).
- Frontend pins `typescript@5`: `openapi-typescript` needs the TS 5 JS API, which TS 7 lacks.
- `mermaid` is pinned to the exact version 12.3.0. Tests use `httpx`; Starlette's TestClient prints a harmless deprecation warning.
- Record deviations from SPEC.md here, then update SPEC.md.
- M10: **no pre-job reuse shortcut for folders.** A fingerprint needs a scan, so the job runs and the store returns the existing entry: no duplicate, but the analysis is repeated. A cheaper check could come later.
- M10: both `url` and `path` is `INVALID_PATH`; neither is `VALIDATION_ERROR` (keeps the old behaviour of an empty body). The spec said "neither: `INVALID_PATH`"; SPEC corrected.
- M10: the folder browser lists every readable directory on the machine (decision 6). `is_repo` hint = has `.git` or a manifest.
- M11: relations are listed at the box's **own level**, not the viewed depth, so the panel is stable when the depth changes and shows a hub's incoming edges (which the flowchart leaves out). Only the hub flag depends on the viewed depth.
- M11: no backend model change, so no tool-version bump and no regeneration of old diagrams.
- M11: C4 is clickable too (its ids are the plain alias, `mmd-N-<id>`), not only flowcharts.
