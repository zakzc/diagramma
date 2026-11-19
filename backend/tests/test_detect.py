from app.render.c4 import RenderMeta, render_c4
from tests.helpers import COMPOSE_MONOREPO, model_of


def by_id(items):
    return {i.id: i for i in items}


def test_compose_monorepo(tmp_path):
    m = model_of(tmp_path, COMPOSE_MONOREPO, "shop")
    c = by_id(m.containers)
    assert set(c) == {"api", "web"}
    assert c["api"].kind == "api" and c["api"].technology == "Python / FastAPI"
    assert c["api"].path == "backend" and c["api"].description == "Shop API"
    assert c["web"].kind == "webapp" and c["web"].technology == "TypeScript / React"
    assert any("docker-compose service 'api'" in e for e in c["api"].evidence)

    e = by_id(m.externals)
    assert {k: (v.kind, v.name) for k, v in e.items()} == {
        "postgres": ("database", "PostgreSQL"),
        "redis": ("database", "Redis"),
        "stripe": ("system", "Stripe"),
        "svc_proxy": ("system", "proxy"),
    }
    assert e["postgres"].evidence  # every element keeps evidence

    rels = {(r.source, r.target): r for r in m.relations}
    assert rels[("api_repositories", "postgres")].label == "Reads/writes"  # import psycopg2
    assert rels[("api_services", "stripe")].technology == "HTTPS"  # import stripe
    assert ("api_repositories", "redis") in rels  # compose-only evidence -> repository component
    assert ("web_api", "api_routes") in rels  # compose depends_on, web -> api
    assert not any(r.target in {"web", "web_core"} and r.source == "svc_proxy" for r in m.relations)


def test_npm_workspaces_and_sibling_dependency(tmp_path):
    m = model_of(
        tmp_path,
        {
            "package.json": '{"name":"root","workspaces":["packages/*"]}',
            "packages/server/package.json": (
                '{"name":"@acme/server","dependencies":{"express":"4","@acme/shared":"*","pg":"8"}}'
            ),
            "packages/server/src/index.ts": "x\n",
            "packages/shared/package.json": '{"name":"@acme/shared"}',
            "packages/shared/src/util.ts": "x\n",
            "packages/cli/package.json": '{"name":"cli","bin":{"cli":"bin.js"}}',
            "packages/cli/index.js": "x\n",
        },
    )
    c = by_id(m.containers)
    assert set(c) == {"server", "shared", "cli"}  # root aggregator is not a container
    assert (c["server"].kind, c["shared"].kind, c["cli"].kind) == ("api", "library", "cli")
    assert {(r.source, r.target) for r in m.relations} == {
        ("server_core", "shared_core"),  # bare import of the sibling package '@acme/shared'
        ("server_core", "postgres"),  # 'pg' dependency; no import evidence in the sample
    }


def test_single_container_fallback(tmp_path):
    m = model_of(tmp_path, {"src/a.py": "x\n", "src/b.py": "x\n"}, "tool")
    assert [(c.id, c.name, c.path, c.kind) for c in m.containers] == [
        ("tool", "tool", ".", "library")
    ]
    assert m.externals == [] and m.relations == []


def test_loose_root_source_next_to_subpackage(tmp_path):
    m = model_of(
        tmp_path,
        {"main.py": "x\n", "web/package.json": '{"dependencies":{"vue":"3"}}', "web/a.js": "x\n"},
        "mix",
    )
    assert {(c.name, c.path) for c in m.containers} == {("mix", "."), ("web", "web")}


def test_env_example_and_scheme_detection(tmp_path):
    m = model_of(
        tmp_path,
        {
            "requirements.txt": "flask==3\n",
            "app.py": "x\n",
            ".env.example": "DATABASE_URL=postgresql://u:p@h/db\nKAFKA_BROKERS=k:9092\n",
        },
    )
    assert {e.id: e.kind for e in m.externals} == {"postgres": "database", "kafka": "queue"}


def test_unsupported_language_gets_warning(tmp_path):
    m = model_of(tmp_path, {"cmd/main.go": "package main\n", "go.mod": "module x\n"}, "gosvc")
    assert len(m.containers) == 1
    assert any("Unsupported language" in w and "go" in w for w in m.warnings)


def test_broken_manifest_is_a_warning_not_a_crash(tmp_path):
    m = model_of(tmp_path, {"package.json": "{not json", "a.js": "x\n"})
    assert len(m.containers) == 1 and any("package.json" in w for w in m.warnings)


META = RenderMeta("o/shop", None, "a" * 40, "2026-01-02T03:04:05+00:00", "0.1.0")


def test_render_golden_and_deterministic(tmp_path):
    from pathlib import Path

    from app.render.flowchart import render_flowchart

    model = model_of(tmp_path / "a", COMPOSE_MONOREPO, "shop")
    again = model_of(tmp_path / "b", COMPOSE_MONOREPO, "shop")
    for name, fn in (("c4", render_c4), ("flowchart", render_flowchart)):
        text = fn(model, META)
        golden = Path(__file__).parent / "golden" / f"compose_monorepo_{name}.mmd"
        if not golden.exists():
            golden.write_text(text)
        assert text == golden.read_text()
        assert fn(again, META) == text  # same input -> byte-identical output


def test_render_escapes_hostile_names(tmp_path):
    m = model_of(
        tmp_path,
        {"package.json": '{"name":"a\\"b","description":"x\\ny \\"q\\" {z}"}', "i.js": "x\n"},
    )
    text = render_c4(m, META)
    assert '"q"' not in text and "\n y" not in text
    assert text.count('"') % 2 == 0


def test_compose_dockerfile_folder_names_the_container(tmp_path):
    m = model_of(
        tmp_path,
        {
            "compose.yml": (
                "services:\n  backend:\n    build:\n      context: .\n"
                "      dockerfile: backend/Dockerfile\n"
            ),
            "backend/pyproject.toml": '[project]\nname = "app"\ndependencies = ["fastapi"]\n',
            "backend/app/main.py": "x\n",
        },
    )
    assert [(c.id, c.path, c.kind) for c in m.containers] == [("backend", "backend", "api")]


def test_compose_dockerfile_folder_without_code_keeps_context(tmp_path):
    m = model_of(
        tmp_path,
        {
            "scripts/docker/compose.yaml": (
                "services:\n  dev:\n    build:\n      context: ../../\n"
                "      dockerfile: scripts/docker/Dockerfile\n"
            ),
            "pyproject.toml": '[project]\nname = "lib"\n',
            "lib/a.py": "x\n",
        },
    )
    assert [(c.name, c.path) for c in m.containers] == [("dev", ".")]
