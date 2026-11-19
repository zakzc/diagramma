import re

import pytest

from app.errors import AppError
from app.models import Model, Relation
from app.render.c4 import RenderMeta
from app.render.layers import analyze_layers, render_layers
from tests.helpers import COMPOSE_MONOREPO, model_of
from tests.nested_sample import NESTED

META = RenderMeta("o/w", "main", "c" * 40, "2026-01-02T03:04:05+00:00", "0.3.0")

CYCLIC = {
    "package.json": '{"name":"cyc"}',
    "src/a.ts": "import './b'\n",
    "src/b.ts": "import './a'\n",  # a <-> b
    "src/c.ts": "import './a'\nimport './b'\n",
    "src/solo.ts": "export const x = 1\n",
}


def edge_lines(text):
    return [ln.strip() for ln in text.splitlines() if "-->" in ln]


def test_layers_follow_the_import_direction(tmp_path):
    m = model_of(tmp_path, NESTED, "w")
    a = analyze_layers(m, 3)
    lay = a.layering.layer
    assert lay["w_core"] == 4 and lay["w_api_routes_users"] == 3  # entry point on top
    assert lay["w_db_models_user"] == 0 and lay["w_api_deps"] == 0  # foundations at the bottom
    assert lay["postgres"] == 0  # external systems depend on nothing
    assert all(lay[s] > lay[t] for s, t in a.layering.drawn)
    s = a.summary
    assert (s.layer_count, s.longest_chain, s.nodes, s.edges_drawn) == (5, 5, 10, 10)
    assert s.layer_sizes == [4, 1, 2, 2, 1] and s.upward_edges == 0 and s.top_upward == []


def test_text_shows_layer_numbers_colours_and_edges_importer_to_imported(tmp_path):
    m = model_of(tmp_path, NESTED, "w")
    text = render_layers(m, META, 3)
    assert text.startswith("flowchart TB\n")
    assert 'w_core["Core<br/>L4"]' in text and 'w_db_models_user["User<br/>L0"]' in text
    assert 'postgres[("PostgreSQL")]' in text and "class postgres ext" in text
    assert "w_services_users --> w_db_models_user" in edge_lines(text)
    assert re.search(r"^\s*class [\w,]*w_core[\w,]* lay4$", text, flags=re.M)
    assert "| depth: 3" in text and "5 layers, 10 nodes, 10 edges drawn" in text


def test_isolated_components_are_counted_not_drawn(tmp_path):
    text = render_layers(model_of(tmp_path, NESTED, "w"), META, 3)
    assert "w_shared_a_b_c_leaf" not in text  # imports nothing, imported by nothing
    assert "2 isolated" in text


def test_import_cycles_become_upward_edges_that_are_counted_not_drawn(tmp_path):
    m = model_of(tmp_path, CYCLIC, "cyc")
    a = analyze_layers(m, 2)
    s = a.summary
    assert s.upward_edges == 1 and len(s.top_upward) == 1
    up = s.top_upward[0]
    assert {up.source, up.target} == {"A", "B"} and up.strength == 1
    assert s.layer_count == 3  # c above the pair, which is ordered rather than collapsed
    text = render_layers(m, META, 2, a)
    assert re.search(r'^\s*cyc_core_[ab]\["[AB]<br/>L\d · ↑1"\]$', text, flags=re.M)
    assert re.search(r"^\s*class [\w,]*cyc_core_a[\w,]* cyc$", text, flags=re.M)  # dashed marker
    drawn = edge_lines(text)
    assert sorted(drawn) == ["cyc_core_a --> cyc_core_b", "cyc_core_c --> cyc_core_a"]
    # c -> b is implied by c -> a -> b, so the transitive reduction drops it
    assert a.summary.edges_transitive_omitted == 1
    assert "1 upward (not drawn)" in text


def test_only_import_derived_edges_are_used(tmp_path):
    a = analyze_layers(model_of(tmp_path, COMPOSE_MONOREPO, "shop"), 2)
    nodes = set(a.layering.layer)
    assert "redis" not in nodes  # only reachable through compose depends_on
    assert {"postgres", "stripe"} <= nodes  # `import psycopg2` / `import stripe`
    assert ("web_api_client", "api_routes") not in a.layering.forward  # compose-only edge


def test_containers_are_named_when_there_are_several(tmp_path):
    text = render_layers(model_of(tmp_path, COMPOSE_MONOREPO, "shop"), META, 2)
    assert "[api]" in text and "[web]" in text
    single = render_layers(model_of(tmp_path / "s", NESTED, "w"), META, 3)
    assert "[w]" not in single


def test_a_model_with_no_import_relations_says_so(tmp_path):
    m = model_of(tmp_path, {"package.json": '{"name":"w"}', "src/a.ts": "x\n"}, "w")
    text = render_layers(m, META, 1)
    assert 'none["No import relations at this depth"]' in text
    assert analyze_layers(m, 1).summary.layer_count == 0


def test_models_generated_before_provenance_are_refused_with_a_clear_message():
    m = Model(system_name="s", relations=[Relation(source="a", target="b", label="Uses")])
    with pytest.raises(AppError) as e:
        analyze_layers(m, 1)
    assert e.value.code == "LAYERS_UNAVAILABLE" and "Submit the repository again" in e.value.message


def test_depth_changes_the_graph_and_output_is_deterministic(tmp_path):
    a, b = model_of(tmp_path / "a", NESTED, "w"), model_of(tmp_path / "b", NESTED, "w")
    texts = {d: render_layers(a, META, d) for d in (1, 2, 3)}
    assert len(set(texts.values())) == 3
    for d, t in texts.items():
        assert t == render_layers(b, META, d)


def test_names_are_escaped(tmp_path):
    files = {
        "package.json": '{"name":"w"}',
        "src/x/a.ts": "import '../y/b'\n",
        "src/y/b.ts": "x\n",
    }
    m = model_of(tmp_path, files, "w")
    m.containers[0].components[0].name = 'Evil "name" {x}'
    text = render_layers(m, META, 1)
    assert '"name"' not in text and text.count('"') % 2 == 0


def test_nested_golden_files(tmp_path):
    """Expected text per depth; the frontend also parses these with the pinned Mermaid."""
    from pathlib import Path

    golden = Path(__file__).parent / "golden"
    for name, files in (("nested", NESTED), ("cyclic", CYCLIC)):
        m = model_of(tmp_path / name, files, "w" if name == "nested" else "cyc")
        for d in range(1, (3 if name == "nested" else 2) + 1):
            text = render_layers(m, META, d)
            path = golden / f"{name}_layers_depth{d}.mmd"
            if not path.exists():
                path.write_text(text)
            assert text == path.read_text(), path.name
