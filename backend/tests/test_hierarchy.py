import pytest

from app.analysis import components as comp_mod
from app.analysis.scan import scan_repo
from app.render.view import max_depth
from tests.helpers import make_repo, model_of
from tests.nested_sample import NESTED


def tree(m):
    """{(depth, name): component} for the first container."""
    return {(k.depth, k.name): k for k in m.containers[0].components}


def test_folders_nest_into_a_tree_with_files_at_the_bottom(tmp_path):
    m = model_of(tmp_path, NESTED, "w")
    t = tree(m)
    assert max_depth(m) == 3
    assert {n for (d, n) in t if d == 1} == {"API", "DB", "Services", "Shared / A / B / C", "Core"}
    routes = t[(2, "Routes")]
    assert (routes.kind, routes.parent, routes.file_count) == ("group", "w_api", 2)
    assert t[(3, "Users")].kind == "file" and t[(3, "Users")].parent == routes.id
    assert t[(2, "Deps")].kind == "file" and t[(2, "Deps")].parent == "w_api"
    assert t[(1, "Core")].kind == "folder" and t[(1, "Core")].paths == ["src"]  # lone root file


def test_pass_through_folders_are_merged_into_one_level(tmp_path):
    m = model_of(tmp_path, NESTED, "w")
    group = tree(m)[(1, "Shared / A / B / C")]  # shared/a/b/c: three folders with nothing else
    assert group.paths == ["src/shared/a/b/c"] and group.kind == "group"
    assert {k.name for k in m.containers[0].components if k.parent == group.id} == {"Leaf", "Leaf2"}


def test_roles_are_inherited_down_the_tree(tmp_path):
    t = tree(model_of(tmp_path, NESTED, "w"))
    assert t[(1, "API")].role == "controller" and t[(2, "Routes")].role == "controller"
    assert t[(3, "Users")].role == "controller"  # a file in routes/ is part of the request layer
    assert t[(2, "Models")].role == "model" and t[(3, "User")].role == "model"
    assert t[(2, "Client")].role == "repository"  # inherited from db/
    assert t[(1, "Shared / A / B / C")].role == "other"


def test_every_scanned_file_maps_to_a_leaf_and_ids_are_unique(tmp_path):
    root = make_repo(tmp_path, NESTED)
    scan = scan_repo(root)
    used: set[str] = set()
    from app.analysis.build import _load_compose
    from app.analysis.containers import detect_containers

    detected = detect_containers(root, scan, "w", _load_compose(root, scan, []), [], used)
    file_comp = comp_mod.detect_components(detected, scan, used)
    comps = detected[0].container.components
    ids = [k.id for k in comps]
    assert len(ids) == len(set(ids))
    parents = {k.parent for k in comps if k.parent}
    assert parents <= set(ids)
    seen: set[str] = set()
    for k in comps:  # parents are always listed before their children
        assert k.parent is None or k.parent in seen
        seen.add(k.id)
    leaves = {k.id for k in comps if k.id not in parents}
    assert {f.path for f in scan.files} == set(file_comp)
    assert set(file_comp.values()) <= leaves
    assert detected[0].container.components[0].weight >= 1


def test_group_sizes_add_up(tmp_path):
    m = model_of(tmp_path, NESTED, "w")
    comps = m.containers[0].components
    for g in (k for k in comps if k.kind == "group"):
        kids = [k for k in comps if k.parent == g.id]
        assert g.file_count == sum(k.file_count for k in kids)
        assert g.weight >= len(kids)


def test_big_containers_get_folder_level_leaves(tmp_path, monkeypatch):
    """Over FILE_LEVEL_MAX_FILES files, leaves are folders; a group keeps its direct files
    together as one "Files" leaf instead of one component per file."""
    monkeypatch.setattr(comp_mod, "FILE_LEVEL_MAX_FILES", 5)
    files = {"package.json": '{"name":"w"}'}
    for name in ("a", "b", "c"):
        files[f"src/web/{name}.ts"] = "x\n"
    for name in ("p", "q"):
        files[f"src/web/inner/{name}.ts"] = "x\n"
    files["src/other/z.ts"] = "x\n"
    t = tree(model_of(tmp_path, files, "w"))
    assert t[(1, "Web")].kind == "group"
    assert t[(2, "Inner")].kind == "folder" and t[(2, "Inner")].file_count == 2  # no per-file split
    assert t[(2, "Files")].kind == "folder" and t[(2, "Files")].file_count == 3
    assert not any(k.kind == "file" for k in t.values())
    assert (1, "Other") in t  # a one-file folder stays a single leaf


def test_small_folders_are_not_split_in_folder_level_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(comp_mod, "FILE_LEVEL_MAX_FILES", 0)
    monkeypatch.setattr(comp_mod, "MIN_SPLIT_FILES", 4)
    files = {"package.json": '{"name":"w"}'}
    for i in range(2):
        files[f"src/small/sub/f{i}.ts"] = "x\n"  # only 2 files: stays one leaf
    for i in range(5):
        files[f"src/large/sub/f{i}.ts"] = "x\n"
    files["src/large/sub/deep/g.ts"] = "x\n"
    t = tree(model_of(tmp_path, files, "w"))
    assert t[(1, "Small / Sub")].kind == "folder"
    assert t[(1, "Large / Sub")].kind == "group"  # 6 files with a sub-folder: split
    assert t[(2, "Deep")].kind == "folder" and t[(2, "Files")].file_count == 5


def test_depth_is_capped_and_deeper_files_fold_into_the_last_level(tmp_path, monkeypatch):
    monkeypatch.setattr(comp_mod, "MAX_DEPTH", 2)
    files = {"package.json": '{"name":"w"}'}
    for lvl in ("one", "two"):
        for i in range(2):
            files[f"src/top/{lvl}/deeper/still/f{lvl}{i}.ts"] = "x\n"
    files["src/top/own.ts"] = "x\n"
    m = model_of(tmp_path, files, "w")
    assert max_depth(m) == 2
    deepest = [k for k in m.containers[0].components if k.depth == 2]
    assert sum(k.file_count for k in deepest) == 5  # nothing lost below the cap


def test_empty_init_files_are_not_components_but_stay_mapped(tmp_path):
    m = model_of(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "p"\n',
            "p/__init__.py": "",
            "p/pkg/__init__.py": "",
            "p/pkg/a.py": "x\n",
            "p/pkg/b.py": "x\n",
            "p/main.py": "from p import pkg\n",
        },
        "p",
    )
    names = {k.name for k in m.containers[0].components}
    assert (
        "Init" not in names
        and "  Init" not in names
        and not any("init" in n.lower() for n in names)
    )
    # `from p import pkg` resolves to p/pkg/__init__.py: the edge must survive
    assert any(r.target.startswith("p_pkg") for r in m.relations)


@pytest.mark.parametrize("n_files", [1, 2])
def test_single_file_folders_are_one_leaf(tmp_path, n_files):
    files = {"package.json": '{"name":"w"}', "src/x.ts": "x\n"}
    for i in range(n_files):
        files[f"src/solo/f{i}.ts"] = "x\n"
    t = tree(model_of(tmp_path, files, "w"))
    assert t[(1, "Solo")].kind == ("folder" if n_files == 1 else "group")
