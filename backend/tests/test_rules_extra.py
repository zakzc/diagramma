"""Rules not exercised by the milestone tests: error mapping, manifest variants, fallbacks."""

import os

import pytest

from app.analysis import fetch
from app.analysis.manifests import (
    has_workspace_file,
    parse_compose,
    parse_package_json,
    parse_pyproject,
    parse_requirements,
)
from app.analysis.scan import scan_repo
from app.render.c4 import RenderMeta, render_c4
from app.render.escape import label, make_id
from app.render.flowchart import render_flowchart
from tests.helpers import model_of

META = RenderMeta("o/r", "dev", "b" * 40, "2026-01-02T03:04:05+00:00", "0.1.0")


# --- git error mapping and token hygiene ---------------------------------------------------


@pytest.mark.parametrize(
    ("stderr", "token", "code"),
    [
        ("fatal: couldn't find remote ref nope", None, "CLONE_FAILED"),
        ("remote: Repository not found.\nfatal: ...", None, "REPO_NOT_FOUND"),
        ("fatal: 'x' does not appear to be a git repository", None, "REPO_NOT_FOUND"),
        ("fatal: could not read Username for 'https://github.com'", None, "AUTH_REQUIRED"),
        ("fatal: terminal prompts disabled", None, "AUTH_REQUIRED"),
        ("fatal: Authentication failed for 'https://github.com/o/r.git/'", "tok", "AUTH_REQUIRED"),
        ("error: RPC failed; HTTP 403", None, "AUTH_REQUIRED"),
        ("fatal: something else entirely", None, "CLONE_FAILED"),
        ("", None, "CLONE_FAILED"),
    ],
)
def test_git_errors_map_to_api_codes(stderr, token, code):
    assert fetch._map_git_error(stderr, token).code == code


def test_auth_hint_depends_on_whether_a_token_is_set():
    anon = fetch._map_git_error("could not read Username", None).message
    authed = fetch._map_git_error("Authentication failed", "tok").message
    assert "set GITHUB_TOKEN" in anon and "check GITHUB_TOKEN" in authed


def test_token_never_reaches_messages_or_argv():
    secret = "ghp_SECRET123"
    err = fetch._map_git_error(f"fatal: bad credentials {secret} at remote", secret)
    assert secret not in err.message and "***" in err.message
    env = fetch._git_env(secret)
    assert env["GIT_TERMINAL_PROMPT"] == "0"  # fail instead of prompting
    assert secret not in " ".join(env[k] for k in env if k.startswith("GIT_CONFIG_KEY"))
    assert "x-access-token" not in fetch._git_env(None).get("GIT_CONFIG_VALUE_0", "")
    assert fetch._git_env(None).get("GIT_CONFIG_COUNT") is None or "GIT_CONFIG_COUNT" in os.environ


# --- manifest variants -----------------------------------------------------------------------


def test_requirements_parsing():
    info = parse_requirements(
        "# c\nFastAPI[all]>=0.1  # inline\n-r other.txt\n\nSQLAlchemy==2.0 ; python_version>'3'\n"
        "psycopg2_binary\nuvicorn @ https://x/y.whl\n",
        ".", "requirements.txt",
    )  # fmt: skip
    assert info.deps == {"fastapi", "sqlalchemy", "psycopg2-binary", "uvicorn"}


def test_pyproject_poetry_and_pep621():
    poetry = parse_pyproject(
        '[tool.poetry]\nname="p"\ndescription="d"\n[tool.poetry.dependencies]\npython="^3.12"\n'
        'Flask="*"\n[tool.poetry.scripts]\ncli="p:main"\n',
        ".", "pyproject.toml",
    )  # fmt: skip
    assert (poetry.name, poetry.description, poetry.deps, poetry.has_bin) == (
        "p",
        "d",
        {"flask"},
        True,
    )
    pep = parse_pyproject(
        '[project]\nname="q"\ndependencies=["a>=1"]\n[project.optional-dependencies]\nx=["b"]\n'
        '[dependency-groups]\ndev=["pytest", {include-group="x"}]\n',
        ".", "pyproject.toml",
    )  # fmt: skip
    assert pep.deps == {"a"} and pep.dev_deps == {"b", "pytest"} and not pep.has_bin


def test_package_json_variants():
    info = parse_package_json(
        '{"name":"n","workspaces":{"packages":["a/*"]},"scripts":{"dev":"x"},'
        '"dependencies":{"Express":"4"},"devDependencies":{"vite":"5"}}',
        "app", "app/package.json",
    )  # fmt: skip
    assert (
        info.workspaces
        and info.has_start
        and info.deps == {"express"}
        and info.dev_deps == {"vite"}
    )
    with pytest.raises(ValueError):
        parse_package_json("[]", ".", "package.json")


def test_pnpm_workspace_file():
    assert has_workspace_file("packages:\n  - 'apps/*'\n")
    assert not has_workspace_file("packages: []\n") and not has_workspace_file("- x\n")


def test_compose_forms():
    svcs = parse_compose(
        """
services:
  a: {build: ./a, environment: {K: v, EMPTY: null}, depends_on: {b: {condition: service_started}}}
  b: {image: "redis:7", environment: ["X=1", "BARE"]}
  c: {build: {context: ../../outside}}
  d: {build: {context: ., dockerfile: svc/d/Dockerfile}}
  e: "not a mapping"
""",
        "deploy/compose.yml",
    )  # fmt: skip
    assert svcs["a"].build_context == "deploy/a" and svcs["a"].depends_on == ["b"]
    assert svcs["a"].env == {"K": "v", "EMPTY": ""}
    assert svcs["b"].image == "redis:7" and svcs["b"].env == {"X": "1", "BARE": ""}
    assert svcs["c"].build_context is None  # escapes the repository: ignored
    assert (svcs["d"].build_context, svcs["d"].dockerfile_dir) == ("deploy", "deploy/svc/d")
    assert "e" not in svcs
    assert parse_compose("not: compose", "c.yml") == {} and parse_compose("[1]", "c.yml") == {}


# --- classification, merging, fallbacks -------------------------------------------------------


def kinds(m):
    return {c.id: c.kind for c in m.containers}


def test_container_kinds(tmp_path):
    m = model_of(
        tmp_path,
        {
            "web/package.json": '{"name":"web","devDependencies":{"svelte":"4"}}',
            "web/a.js": "x\n",
            "api/pyproject.toml": '[project]\nname="api"\ndependencies=["fastapi","celery"]\n',
            "api/a.py": "x\n",
            "worker/requirements.txt": "celery\n",
            "worker/a.py": "x\n",
            "tool/package.json": '{"name":"tool","dependencies":{"commander":"1"}}',
            "tool/a.js": "x\n",
            "svc/package.json": '{"name":"svc","scripts":{"start":"node a.js"}}',
            "svc/a.js": "x\n",
            "lib/package.json": '{"name":"lib"}',
            "lib/a.js": "x\n",
        },
    )
    assert kinds(m) == {
        "web": "webapp", "api": "api", "worker": "worker", "tool": "cli", "svc": "service",
        "lib": "library",
    }  # fmt: skip


def test_python_and_node_manifests_in_one_folder_merge(tmp_path):
    m = model_of(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname="py"\ndependencies=["fastapi"]\n',
            "package.json": '{"name":"js","dependencies":{"react":"18"}}',
            "src/a.py": "x\n",
        },
    )
    assert len(m.containers) == 1 and m.containers[0].kind == "webapp"  # UI framework wins


def test_sibling_package_import_in_code_draws_an_edge_to_its_core(tmp_path):
    m = model_of(
        tmp_path,
        {
            "app/package.json": '{"name":"app"}',
            "app/src/ui/a.ts": "import { x } from '@acme/shared/utils'\nimport y from 'left-pad'\n",
            "shared/package.json": '{"name":"@acme/shared"}',
            "shared/src/index.ts": "x\n",
        },
    )
    assert [(r.source, r.target) for r in m.relations] == [("app_ui", "shared_core")]


def test_queue_from_compose_and_container_level_fallback_edges(tmp_path):
    m = model_of(
        tmp_path,
        {
            "compose.yml": (
                "services:\n  api: {build: ./api, depends_on: [mq, worker]}\n"
                "  worker: {build: ./worker}\n  mq: {image: 'rabbitmq:3'}\n"
            ),
            "api/pyproject.toml": '[project]\nname="api"\ndependencies=["fastapi"]\n',
            "api/app/main.py": "x\n",
            "worker/pyproject.toml": '[project]\nname="worker"\ndependencies=["celery"]\n',
            "worker/app/job.py": "x\n",
        },
    )
    assert {e.id: e.kind for e in m.externals} == {"rabbitmq": "queue"}
    rels = {(r.source, r.target): r.label for r in m.relations}
    assert rels[("api_core", "rabbitmq")] == "Publishes/consumes"
    assert ("api_core", "worker_core") in rels  # no imports, so compose depends_on is the evidence


def test_container_without_source_files_is_drawn_as_a_plain_container(tmp_path):
    m = model_of(
        tmp_path,
        {
            "compose.yml": "services:\n  proxy: {build: ./proxy}\n  api: {build: ./api}\n",
            "proxy/Dockerfile": "FROM nginx\n",
            "api/package.json": '{"name":"api"}',
            "api/a.js": "x\n",
        },
    )
    by = {c.id: c for c in m.containers}
    assert by["proxy"].components == [] and by["api"].components
    text = render_c4(m, META)
    assert "Container(proxy," in text and "Container_Boundary(api," in text


def test_container_only_diagram_falls_back_to_c4container_and_flowchart_nodes(tmp_path):
    m = model_of(
        tmp_path,
        {
            "compose.yml": "services:\n  a: {build: ./a}\n  mq: {image: kafka}\n",
            "a/Dockerfile": "FROM x\n",
        },
    )
    c4, flow = render_c4(m, META), render_flowchart(m, META)
    assert c4.startswith("C4Container") and "ContainerQueue(kafka," in c4
    assert "title Container diagram" in c4 and "Container_Boundary" not in c4
    assert 'a["a<br/>[Container: Docker]"]' in flow and 'kafka(["Kafka' in flow
    assert "class a container" in flow and "class kafka store" in flow


def test_scan_ignores_symlinks(tmp_path):
    (tmp_path / "real.py").write_text("x\n")
    (tmp_path / "link.py").symlink_to(tmp_path / "real.py")
    (tmp_path / "linkdir").symlink_to(tmp_path)
    assert [f.path for f in scan_repo(tmp_path).files] == ["real.py"]


def test_escaping_helpers():
    used: set[str] = set()
    assert make_id("end", used) == "n_end" and make_id("9lives", used) == "n_9lives"
    assert make_id("a-b c", used) == "a_b_c" and make_id("a b c", used) == "a_b_c_2"
    assert make_id("!!!", used) == "x"
    assert label('He said "hi" {x} `y` \\ %%') == "He said 'hi' (x) 'y' / %"
    assert label("x" * 300).endswith("…") and len(label("x" * 300)) == 120
    assert label(None) == ""
