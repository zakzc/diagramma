from app.analysis.reduce import reduce_components
from app.models import Component, Container, Model, Relation


def comp(i, w):
    return Component(id=i, name=i.upper(), role="other", weight=w, paths=[f"src/{i}"])


def test_cap_merges_smallest_and_remaps_relations():
    c = Container(
        id="api", name="API", kind="api", technology="Python",
        path=".", components=[comp(f"c{i}", i + 1) for i in range(8)],
    )  # fmt: skip
    m = Model(
        system_name="s",
        containers=[c],
        relations=[
            Relation(source="c7", target="c0", label="Uses", strength=2),
            Relation(source="c7", target="c1", label="Calls", strength=3),
            Relation(source="c0", target="c1", label="Uses"),  # becomes a self edge
        ],
    )
    reduce_components(m, cap=5)
    ids = {k.id for k in c.components}
    assert len(ids) == 5 and "api_other" in ids and "c7" in ids  # heaviest survives
    assert [(r.source, r.target, r.strength) for r in m.relations] == [("c7", "api_other", 5)]
    assert m.relations[0].label == "Uses"  # mixed labels collapse to a neutral one
    assert any("Merged 4 smallest" in w for w in m.warnings)


def test_under_cap_is_untouched_and_unreducible_is_reported():
    c = Container(id="a", name="A", kind="api", technology="x", path=".", components=[comp("k", 1)])
    m = Model(system_name="s", containers=[c])
    reduce_components(m, cap=60)
    assert m.warnings == []
    reduce_components(m, cap=0)
    assert any("too many containers" in w for w in m.warnings)


def test_cap_applies_across_containers_to_the_busiest():
    big = Container(
        id="big", name="Big", kind="api", technology="x", path="a",
        components=[comp(f"b{i}", i + 1) for i in range(6)],
    )  # fmt: skip
    small = Container(
        id="sm",
        name="Sm",
        kind="api",
        technology="x",
        path="b",
        components=[comp("s0", 1), comp("s1", 1)],
    )
    m = Model(system_name="s", containers=[big, small])
    reduce_components(m, cap=5)
    assert len(small.components) == 2 and len(big.components) == 3
