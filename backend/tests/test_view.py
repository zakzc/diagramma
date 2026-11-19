from app.models import Component, Container, External, Model, Relation
from app.render.view import AUTO_CAP, ViewNode, auto_depth, build_view, max_depth
from tests.helpers import model_of, view_edges
from tests.nested_sample import NESTED


def comp(id_, depth, parent=None, role="other", name=None):
    return Component(
        id=id_, name=name or id_, role=role, depth=depth, parent=parent, weight=1, file_count=1
    )


def small_model() -> Model:
    """a (group) -> a1, a2 ; b (leaf at level 1) ; relations only between leaves."""
    comps = [comp("a", 1), comp("a1", 2, "a"), comp("a2", 2, "a"), comp("b", 1)]
    comps[0].kind = "group"
    return Model(
        system_name="s",
        containers=[
            Container(id="c", name="C", kind="api", technology="Py", path=".", components=comps)
        ],
        externals=[External(id="db", name="DB", kind="database")],
        relations=[
            Relation(source="a1", target="b", label="Uses", strength=2),
            Relation(source="a2", target="b", label="Uses", strength=3, technology="X"),
            Relation(source="a1", target="a2", label="Uses"),
            Relation(source="b", target="db", label="Reads/writes", technology="SQL"),
        ],
    )  # fmt: skip


def test_depth_one_rolls_leaves_up_and_sums_strength():
    v = build_view(small_model(), 1)
    assert [n.comp.id for _, roots in v.containers for n in roots] == ["a", "b"]
    assert all(not n.children for _, roots in v.containers for n in roots)  # nothing expanded
    rels = {(r.source, r.target): r for r in v.relations}
    assert set(rels) == {("a", "b"), ("b", "db")}  # a1 -> a2 is internal to a: dropped
    assert rels[("a", "b")].strength == 5 and rels[("a", "b")].technology == "X"
    assert v.nodes == 2


def test_depth_two_expands_groups_into_nested_nodes():
    v = build_view(small_model(), 2)
    ((_, roots),) = v.containers
    a = next(n for n in roots if n.comp.id == "a")
    assert [c.comp.id for c in a.children] == ["a1", "a2"]
    assert next(n for n in roots if n.comp.id == "b").children == []  # shallower leaf: as is
    assert {(r.source, r.target) for r in v.relations} == {
        ("a1", "b"), ("a2", "b"), ("a1", "a2"), ("b", "db"),
    }  # fmt: skip
    assert v.nodes == 3  # a1, a2, b: the group `a` is a boundary around its two boxes


def test_a_depth_beyond_the_model_equals_the_deepest_view():
    m = small_model()
    assert build_view(m, 9).nodes == build_view(m, 2).nodes == 3
    assert build_view(m, 9).relations == build_view(m, 2).relations


def test_mixed_labels_collapse_to_a_neutral_one():
    m = small_model()
    m.relations[1] = Relation(source="a2", target="b", label="Calls", strength=1)
    rel = next(r for r in build_view(m, 1).relations if (r.source, r.target) == ("a", "b"))
    assert rel.label == "Uses" and rel.strength == 3


def test_views_do_not_modify_the_model():
    m = small_model()
    before = m.model_dump()
    build_view(m, 1)
    assert m.model_dump() == before


def test_max_and_auto_depth_on_real_nesting(tmp_path):
    m = model_of(tmp_path, NESTED, "w")
    assert max_depth(m) == 3
    assert auto_depth(m) == 3  # small: show everything
    # visible components: depth 1 = 5, depth 2 = 9 (incl. the shallower Core leaf), depth 3 = 11
    assert auto_depth(m, cap=10) == 2
    assert auto_depth(m, cap=9) == 2
    assert auto_depth(m, cap=8) == 1
    assert auto_depth(m, cap=5) == 1
    assert auto_depth(m, cap=0) == 1  # never below 1


def test_auto_depth_defaults_to_the_documented_cap():
    assert AUTO_CAP == 60
    flat = Model(system_name="s")
    assert max_depth(flat) == 1 and auto_depth(flat) == 1


def test_edges_stay_consistent_across_depths(tmp_path):
    """Rolling up never invents or loses coupling: total strength to an external is constant."""
    m = model_of(tmp_path, NESTED, "w")
    for d in (1, 2, 3):
        to_pg = sum(r.strength for (s, t), r in view_edges(m, d).items() if t == "postgres")
        assert to_pg == 1
    assert sum(r.strength for r in m.relations) >= sum(
        r.strength for r in build_view(m, 1).relations
    )  # depth 1 only drops edges internal to a component


def test_view_node_count_matches_what_auto_depth_budgets(tmp_path):
    """`nodes` (shown to users) and `auto_depth` (picks the default) must count the same boxes."""
    from app.render.view import _visible_at

    m = model_of(tmp_path, NESTED, "w")
    for d in range(1, max_depth(m) + 1):
        assert build_view(m, d).nodes == _visible_at(m, d), d


def grouped(m: Model, depth: int):
    return {(r.source, r.target): r for r in build_view(m, depth).grouped_relations}


def nested_model() -> Model:
    """c1: a{a1,a2}, b{b1}, z ; c2: x{x1} ; external db.   a1->a2 stays inside a."""

    def g(id_, depth, parent=None):
        k = comp(id_, depth, parent)
        k.kind = "group"
        return k

    c1 = Container(
        id="c1", name="C1", kind="api", technology="Py", path=".",
        components=[g("a", 1), comp("a1", 2, "a"), comp("a2", 2, "a"), g("b", 1),
                    comp("b1", 2, "b"), comp("z", 1)],
    )  # fmt: skip
    c2 = Container(
        id="c2", name="C2", kind="api", technology="Py", path="c2",
        components=[g("x", 1), comp("x1", 2, "x")],
    )  # fmt: skip
    rel = lambda s, t, n=1, label="Uses", tech=None: Relation(  # noqa: E731
        source=s, target=t, label=label, strength=n, technology=tech
    )
    return Model(
        system_name="s", containers=[c1, c2],
        externals=[External(id="db", name="DB", kind="database")],
        relations=[
            rel("a1", "a2"), rel("a1", "b1", 2), rel("a2", "b1", 3), rel("b1", "z"),
            rel("a1", "x1", 1, "Calls", "HTTP"), rel("b1", "db", 1, "Reads/writes", "SQL"),
        ],
    )  # fmt: skip


def test_edges_inside_a_group_stay_between_its_boxes():
    assert ("a1", "a2") in grouped(nested_model(), 2)


def test_edges_between_groups_of_one_container_join_the_sibling_groups():
    g = grouped(nested_model(), 2)
    assert ("a1", "b1") not in g and ("a2", "b1") not in g
    assert g[("a", "b")].strength == 5  # 2 + 3, merged into one thick edge
    assert ("b", "z") in g  # the box z is a direct child of the container


def test_cross_container_and_external_edges_start_at_the_top_level_component():
    g = grouped(nested_model(), 2)
    assert g[("a", "x")].label == "Calls" and g[("a", "x")].technology == "HTTP"
    assert g[("b", "db")].label == "Reads/writes"  # b, not b1: level-1 component -> database


def test_at_depth_one_nothing_is_nested_so_grouping_changes_nothing():
    m = nested_model()
    v = build_view(m, 1)
    assert {(r.source, r.target) for r in v.grouped_relations} == {
        (r.source, r.target) for r in v.relations
    }


def test_grouping_never_draws_an_edge_to_an_ancestor_or_to_itself():
    m = nested_model()
    for d in (1, 2):
        v = build_view(m, d)
        parents = {n.comp.id: n for _, roots in v.containers for n in roots}
        for r in v.grouped_relations:
            assert r.source != r.target
            assert r.target not in {
                c.comp.id for c in parents.get(r.source, ViewNode(comp("_", 1))).children
            }


def test_mixed_labels_in_a_bundle_fall_back_to_the_neutral_one():
    m = nested_model()
    m.relations[1].label = "Calls"  # a1->b1 Calls, a2->b1 Uses -> one a->b edge
    assert grouped(m, 2)[("a", "b")].label == "Uses"


def test_view_edge_count_shown_to_users_matches_the_text_for_each_format(tmp_path):
    from app.render.view import build_view as bv

    m = model_of(tmp_path, NESTED, "w")
    v = bv(m, 3)
    assert len(v.grouped_relations) < len(v.relations)  # that is the point of grouping


def hub_model(users: int, external_users: int = 0) -> Model:
    """`util` plus `users` components that import it, each also importing the next one."""
    comps = [comp("util", 1)] + [comp(f"u{i}", 1) for i in range(users)]
    rels = [Relation(source=f"u{i}", target="util", label="Uses") for i in range(users)]
    rels += [
        Relation(source=f"u{i}", target="db", label="Reads/writes") for i in range(external_users)
    ]
    rels += [Relation(source="util", target="u0", label="Uses")]  # a hub still has outgoing edges
    return Model(
        system_name="s",
        containers=[
            Container(id="c", name="C", kind="api", technology="Py", path=".", components=comps)
        ],
        externals=[External(id="db", name="DB", kind="database")],
        relations=rels,
    )


def hubs_of(m: Model, depth: int = 1):
    from app.render.view import find_hubs

    v = build_view(m, depth)
    return find_hubs(v.grouped_relations, {n.comp.id for _, roots in v.containers for n in roots})


def test_a_component_everyone_depends_on_is_a_hub():
    assert hubs_of(hub_model(12)) == {"util": 12}


def test_hub_needs_both_enough_dependents_and_a_large_share():
    assert hubs_of(hub_model(7)) == {}  # fewer than 8 dependents: never a hub
    assert hubs_of(hub_model(8)) == {"util": 8}
    # 8 dependents out of 40 sources is only 20%: a popular module, not a hub
    m = hub_model(8)
    m.containers[0].components += [comp(f"o{i}", 1) for i in range(33)]
    m.relations += [  # a chain: 32 more sources, none of them depended on by many
        Relation(source=f"o{i}", target=f"o{i + 1}", label="Uses") for i in range(32)
    ]
    assert hubs_of(m) == {}


def test_external_systems_are_never_hubs():
    m = hub_model(12, external_users=12)  # 12 components use the database
    assert "db" not in hubs_of(m)


def test_no_hubs_in_small_or_typical_graphs(tmp_path):
    assert hubs_of(model_of(tmp_path, NESTED, "w"), 3) == {}
