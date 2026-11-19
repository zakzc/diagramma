import random
from collections import defaultdict

import pytest

from app.analysis.layering import MAX_SPAN, layer_graph, order_nodes


def reach(edges):
    adj = defaultdict(set)
    for s, t in edges:
        adj[s].add(t)
    out = {}

    def go(n, seen):
        for d in adj[n]:
            if d not in seen:
                seen.add(d)
                go(d, seen)
        return seen

    nodes = {x for e in edges for x in e}
    for n in nodes:
        out[n] = go(n, set())
    return out


def check_invariants(nodes, edges, r):
    edges = {e: w for e, w in edges.items() if e[0] != e[1]}
    # every edge is either forward or upward, never both, never lost
    assert set(r.forward) | set(r.upward) == set(edges)
    assert not set(r.forward) & set(r.upward)
    # every forward edge strictly decreases the layer; so the forward graph is acyclic
    assert all(r.layer[s] > r.layer[t] for s, t in r.forward)
    # a layer is the longest path to something that depends on nothing
    for n in nodes:
        outs = [t for (s, t) in r.forward if s == n]
        assert r.layer[n] == (0 if not outs else 1 + max(r.layer[t] for t in outs))
    # the reduction keeps exactly the same reachability, and removes only implied edges
    assert reach(set(r.reduced)) == reach(set(r.forward))
    assert set(r.reduced) <= set(r.forward) and set(r.drawn) <= set(r.reduced)
    assert all(not _implied(e, r) for e in r.reduced)
    # nothing is lost silently: every forward edge is drawn or counted
    assert len(r.drawn) + r.transitive_omitted + r.long_omitted == len(r.forward)
    assert all(r.layer[s] - r.layer[t] <= MAX_SPAN for s, t in r.drawn)
    assert all(r.layer[s] - r.layer[t] > MAX_SPAN for s, t in set(r.reduced) - set(r.drawn))


def _implied(e, r):
    """Is forward edge e = (s, t) reachable through another direct dependency of s?"""
    s, t = e
    rc = reach(r.forward)
    return any(t in rc.get(d, set()) for (x, d) in r.forward if x == s and d != t)


def test_cycle_is_broken_into_one_upward_edge_and_the_rest_layers():
    edges = {("a", "b"): 1, ("b", "c"): 1, ("a", "c"): 1, ("c", "a"): 1, ("d", "c"): 1}
    r = layer_graph(["a", "b", "c", "d"], edges)
    assert r.layer == {"c": 0, "b": 1, "a": 2, "d": 1}
    assert sorted(r.upward) == [("c", "a")]
    assert sorted(r.drawn) == [("a", "b"), ("b", "c"), ("d", "c")]
    assert r.transitive_omitted == 1  # a -> c is implied by a -> b -> c
    assert (r.layer_count, r.layer_sizes()) == (3, [1, 2, 1])


def test_a_big_cycle_is_never_collapsed_into_one_node():
    nodes = [f"n{i}" for i in range(15)]
    edges = {(a, b): 1 for a in nodes for b in nodes if a != b}  # everyone imports everyone
    r = layer_graph(nodes, edges)
    assert sorted(r.layer.values()) == list(range(15))  # 15 distinct layers: still ordered
    assert len(r.upward) == 105 and len(r.forward) == 105
    check_invariants(nodes, edges, r)


def test_heavier_edges_are_kept_forward():
    # a and b import each other; a imports b 9 times, b imports a once: a is the dependent
    r = layer_graph(["a", "b"], {("a", "b"): 9, ("b", "a"): 1})
    assert list(r.forward) == [("a", "b")] and list(r.upward) == [("b", "a")]
    assert r.layer == {"a": 1, "b": 0}


def test_long_edges_are_omitted_and_counted_not_lost():
    # top -> a -> b -> c -> d -> w   and   top -> w   (no other route from top to w except
    # through the chain, so this is implied and removed) ; and top2 -> w where top2 is high
    chain = ["top", "a", "b", "c", "d", "w"]
    edges = {(x, y): 1 for x, y in zip(chain, chain[1:], strict=False)}
    edges[("top", "w")] = 1  # implied by the chain: transitive, not long
    nodes = [*chain, "top2", "p", "q", "r", "s"]
    for x, y in (("top2", "p"), ("p", "q"), ("q", "r"), ("r", "s"), ("s", "top")):
        edges[(x, y)] = 1
    edges[("top2", "w")] = 1  # implied as well, via top2 -> ... -> w
    r = layer_graph(nodes, edges)
    assert r.transitive_omitted == 2 and r.long_omitted == 0
    # an edge that is NOT implied but spans many layers: leaf z only reachable directly
    nodes2 = [*chain, "z", "hi"]
    edges2 = {(x, y): 1 for x, y in zip(["hi", *chain], chain, strict=False)}
    edges2[("hi", "z")] = 1  # hi is at layer 6, z at layer 0: span 6, no other path to z
    r2 = layer_graph(nodes2, edges2)
    assert r2.long_omitted == 1 and ("hi", "z") not in r2.drawn and ("hi", "z") in r2.forward
    assert r2.transitive_omitted == 0


def test_empty_single_and_edgeless_graphs():
    assert layer_graph([], {}).layer_count == 0
    r = layer_graph(["only"], {})
    assert r.layer == {"only": 0} and r.layer_count == 1 and not r.drawn
    assert layer_graph(["a", "b"], {}).layer_sizes() == [2]  # all independent: one layer
    assert layer_graph(["a"], {("a", "a"): 3}).upward == {}  # self imports are ignored


def random_graph(seed: int, n: int, density: float):
    rnd = random.Random(seed)
    nodes = [f"n{i}" for i in range(n)]
    edges = {
        (a, b): rnd.randint(1, 5)
        for a in nodes for b in nodes
        if a != b and rnd.random() < density
    }  # fmt: skip
    return nodes, edges


@pytest.mark.parametrize("seed", range(25))
def test_invariants_hold_on_random_graphs(seed):
    nodes, edges = random_graph(seed, 4 + seed % 20, [0.05, 0.15, 0.4][seed % 3])
    check_invariants(nodes, edges, layer_graph(nodes, edges))


@pytest.mark.parametrize("seed", range(8))
def test_result_does_not_depend_on_input_order(seed):
    nodes, edges = random_graph(seed, 18, 0.2)
    a = layer_graph(nodes, edges)
    rnd = random.Random(seed)
    nodes2, items = nodes[:], list(edges.items())
    rnd.shuffle(nodes2)
    rnd.shuffle(items)
    b = layer_graph(nodes2, dict(items))
    assert (a.layer, a.forward, a.upward, a.drawn) == (b.layer, b.forward, b.upward, b.drawn)


def test_order_puts_dependents_first():
    order = order_nodes(["lib", "app", "mid"], {("app", "mid"): 1, ("mid", "lib"): 1})
    assert order == ["app", "mid", "lib"]


def test_acyclic_graphs_have_no_upward_edges():
    nodes, edges = random_graph(3, 20, 0.0)
    nodes = [f"n{i}" for i in range(20)]
    edges = {
        (nodes[i], nodes[j]): 1 for i in range(20) for j in range(i + 1, 20) if (i + j) % 3 == 0
    }
    r = layer_graph(nodes, edges)
    assert r.upward == {} and len(r.forward) == len(edges)
