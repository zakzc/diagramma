"""Every relation records what it rests on, so the Dependency graph can use imports only."""

from tests.helpers import COMPOSE_MONOREPO, model_of, view_edges
from tests.nested_sample import NESTED


def ev(m):
    return {(r.source, r.target): r.evidence for r in m.relations}


def test_import_edges_are_tagged_import(tmp_path):
    assert {tuple(e) for e in ev(model_of(tmp_path, NESTED, "w")).values()} == {("import",)}


def test_compose_only_edges_are_tagged_compose(tmp_path):
    e = ev(model_of(tmp_path, COMPOSE_MONOREPO, "shop"))
    assert e[("api_repositories", "redis")] == ["compose"]  # compose depends_on, no import
    assert e[("web_api_client", "api_routes")] == ["compose"]
    assert e[("api_repositories", "postgres")] == ["import"]  # `import psycopg2` wins
    assert e[("api_services", "stripe")] == ["import"]


def test_manifest_and_env_evidence_are_distinguished(tmp_path):
    m = model_of(
        tmp_path,
        {
            "package.json": '{"name":"app","dependencies":{"pg":"8"}}',  # declared, never imported
            "src/a.ts": "x\n",
            ".env.example": "REDIS_URL=redis://localhost\n",
        },
    )
    e = ev(m)
    assert e[("app_core", "postgres")] == ["manifest"]
    assert e[("app_core", "redis")] == ["env"]


def test_workspace_sibling_in_package_json_only_is_manifest_evidence(tmp_path):
    m = model_of(
        tmp_path,
        {
            "app/package.json": '{"name":"app","dependencies":{"@acme/shared":"*"}}',
            "app/src/a.ts": "x\n",  # does not import it
            "shared/package.json": '{"name":"@acme/shared"}',
            "shared/src/b.ts": "x\n",
        },
    )
    assert list(ev(m).values()) == [["manifest"]]


def test_evidence_survives_the_depth_roll_up_and_edge_grouping(tmp_path):
    m = model_of(tmp_path, COMPOSE_MONOREPO, "shop")
    for depth in (1, 2):
        rel = view_edges(m, depth)
        assert rel[("api_repositories", "postgres")].evidence == ["import"]
        assert rel[("api_repositories", "redis")].evidence == ["compose"]


def test_merged_edges_carry_the_union_of_their_evidence():
    from app.models import Component, Container, Model, Relation
    from app.render.view import build_view

    def c(i, d=1, p=None):
        return Component(id=i, name=i, role="other", depth=d, parent=p, weight=1, file_count=1)

    cont = Container(
        id="k", name="K", kind="api", technology="Py", path=".",
        components=[c("g"), c("g1", 2, "g"), c("g2", 2, "g"), c("z")],
    )  # fmt: skip
    cont.components[0].kind = "group"
    m = Model(
        system_name="s",
        containers=[cont],
        relations=[
            Relation(source="g1", target="z", label="Uses", evidence=["import"]),
            Relation(source="g2", target="z", label="Uses", evidence=["compose"]),
        ],
    )
    (merged,) = build_view(m, 1).relations  # g1 and g2 roll up into g
    assert merged.evidence == ["compose", "import"] and merged.strength == 2


def test_models_stored_before_provenance_have_no_evidence():
    from app.models import Relation

    assert Relation(source="a", target="b", label="Uses").evidence == []
