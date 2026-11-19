import re

from app.render.c4 import RenderMeta, render_c4
from app.render.flowchart import _width, render_flowchart
from app.render.view import auto_depth
from tests.helpers import model_of
from tests.nested_sample import NESTED

META = RenderMeta("o/w", "main", "c" * 40, "2026-01-02T03:04:05+00:00", "0.2.0")


def model(tmp_path):
    return model_of(tmp_path, NESTED, "w")


def subgraph_ids(text):
    return re.findall(r"^\s*subgraph (\w+)\[", text, flags=re.M)


def test_flowchart_nests_groups_and_expands_with_depth(tmp_path):
    m = model(tmp_path)
    d1, d2, d3 = (render_flowchart(m, META, d) for d in (1, 2, 3))
    assert subgraph_ids(d1) == ["w"]  # only the container: groups are plain boxes
    assert "w_api[" in d1 and "w_api_routes" not in d1
    assert subgraph_ids(d2) == ["w", "w_api", "w_db", "w_services", "w_shared_a_b_c"]
    assert "w_api_routes[" in d2  # a group below the cut is a box again
    assert "w_api_routes_users" not in d2
    assert "w_api_routes" in subgraph_ids(d3) and "w_api_routes_users[" in d3
    # nesting: each subgraph is closed, and routes sits inside api
    assert d3.count(" end") == len(subgraph_ids(d3))
    api_block = d3[d3.index("subgraph w_api[") :]
    assert api_block.index("subgraph w_api_routes[") < api_block.index("w_api_deps[")


def test_group_titles_carry_file_counts(tmp_path):
    text = render_flowchart(model(tmp_path), META, 3)
    assert 'subgraph w_api["API<br/>3 files"]' in text
    assert 'subgraph w_api_routes["Routes<br/>2 files"]' in text
    assert 'w_api_routes_users["Users<br/>[Component: TypeScript]"]' in text  # files stay compact


def test_nodes_are_coloured_by_role_and_stores_and_externals_differ(tmp_path):
    text = render_flowchart(model(tmp_path), META, 3)
    assert re.search(r"^\s*class [\w,]*w_api_routes_users[\w,]* controller$", text, flags=re.M)
    assert re.search(r"^\s*class [\w,]*w_db_models_user[\w,]* model$", text, flags=re.M)
    assert re.search(r"^\s*class postgres store$", text, flags=re.M)
    assert "classDef controller fill:" in text and "classDef external fill:" in text
    assert 'postgres[("PostgreSQL' in text  # cylinder


def test_edge_thickness_and_counts_show_coupling(tmp_path):
    d1 = render_flowchart(model(tmp_path), META, 1)
    edges = [ln.strip() for ln in d1.splitlines() if "-->" in ln]
    assert 'w_services -->|"×4"| w_db' in edges  # 4 imports; "Uses" itself is not printed
    idx = edges.index('w_services -->|"×4"| w_db')
    assert f"linkStyle {idx} stroke-width:4px" in d1  # 2 + log2(4)
    assert "w_core --> w_api" in edges  # a single plain import: no label, default width
    single = edges.index("w_core --> w_api")
    assert f"linkStyle {single} " not in d1


def test_default_uses_label_is_never_printed_but_informative_labels_are(tmp_path):
    text = render_flowchart(model(tmp_path), META, 3)
    assert '|"Uses"|' not in text
    assert 'w_db -->|"Reads/writes<br/>[SQL]"| postgres' in text  # kept: says what and how


def edge_lines(text):
    return [ln.strip() for ln in text.splitlines() if "-->" in ln]


def test_cross_group_edges_attach_to_the_groups_not_the_files(tmp_path):
    edges = edge_lines(render_flowchart(model(tmp_path), META, 3))
    # the file-to-file imports across folders collapse onto the folders...
    assert not any("w_api_routes_users" in e and "w_services" in e for e in edges)
    assert 'w_api -->|"×2"| w_services' in edges
    assert 'w_services -->|"×4"| w_db' in edges
    # ...while an edge inside one group keeps its detail
    assert 'w_api_routes -->|"×2"| w_api_deps' in edges
    assert len(edges) == 5  # 10 file-level imports -> 5 readable edges


def test_width_scale():
    assert [_width(n) for n in (1, 2, 3, 4, 8, 64, 10_000)] == [None, 3, 3, 4, 5, 7, 7]


def test_c4_uses_nested_boundaries_only_below_depth_one(tmp_path):
    m = model(tmp_path)
    d1 = render_c4(m, META, 1)
    assert "Boundary(w_api," not in d1 and "Container_Boundary(w," in d1
    d3 = render_c4(m, META, 3)
    assert 'Boundary(w_api_routes, "Routes", "2 files") {' in d3
    assert d3.count("{") == d3.count("}")
    assert "Component(w_api_routes_users," in d3 and "Rel(w_api_routes_users," in d3


def test_default_depth_is_the_auto_depth_and_is_recorded_in_the_header(tmp_path):
    m = model(tmp_path)
    depth = auto_depth(m)
    assert render_flowchart(m, META) == render_flowchart(m, META, depth)
    assert render_c4(m, META) == render_c4(m, META, depth)
    assert f"| depth: {depth}" in render_c4(m, META)
    assert "| depth: 1" in render_flowchart(m, META, 1)


def test_output_is_deterministic_for_every_depth(tmp_path):
    a, b = model(tmp_path / "a"), model(tmp_path / "b")
    for d in (1, 2, 3):
        assert render_flowchart(a, META, d) == render_flowchart(b, META, d)
        assert render_c4(a, META, d) == render_c4(b, META, d)


def test_depths_are_different_diagrams(tmp_path):
    m = model(tmp_path)
    texts = {render_flowchart(m, META, d) for d in (1, 2, 3)}
    assert len(texts) == 3


def test_nested_golden_files(tmp_path):
    """The expected text for the nested sample at every depth; the frontend also checks that
    all of these parse with the pinned Mermaid (src/golden-mermaid.test.ts)."""
    from pathlib import Path

    m = model(tmp_path)
    golden = Path(__file__).parent / "golden"
    for fmt, fn in (("flowchart", render_flowchart), ("c4", render_c4)):
        for d in (1, 2, 3):
            text = fn(m, META, d)
            path = golden / f"nested_{fmt}_depth{d}.mmd"
            if not path.exists():
                path.write_text(text)
            assert text == path.read_text(), path.name


def hub_text(n=12):
    from tests.test_view import hub_model

    return render_flowchart(hub_model(n), META, 1)


def test_a_hub_is_drawn_once_marked_and_without_incoming_edges():
    text = hub_text()
    assert 'util["util<br/>[Component]<br/>used by 12"]' in text
    assert "classDef hub stroke-width:3px,stroke-dasharray:5 3" in text
    assert re.search(r"^\s*class [\w,]*util[\w,]* hub$", text, flags=re.M)
    edges = edge_lines(text)
    assert not any(e.endswith("--> util") or e.endswith("| util") for e in edges)  # not wired in
    assert "util --> u0" in edges  # what the hub itself depends on is still drawn
    assert "%% shared modules, incoming edges not drawn: util" in text


def test_hubs_keep_their_role_colour_and_ordinary_nodes_are_unmarked():
    text = hub_text()
    assert re.search(r"^\s*class [\w,]*util[\w,]* other$", text, flags=re.M)  # role class kept
    assert not re.search(r"^\s*class [\w,]*u3[\w,]* hub$", text, flags=re.M)
    assert "used by" not in hub_text(5)  # below the threshold nothing changes
    assert "shared modules" not in hub_text(5)


def test_c4_still_draws_every_edge_including_those_to_hubs():
    from tests.test_view import hub_model

    text = render_c4(hub_model(12), META, 1)
    assert sum(1 for ln in text.splitlines() if "Rel(" in ln and ", util," in ln) == 12
