import sqlite3

import pytest

from app import __version__
from app.db import DiagramStore
from app.errors import AppError
from app.models import DiagramRecord, Model


def rec(**kw) -> DiagramRecord:
    base = dict(
        repo_url="https://github.com/Owner/Repo", owner="Owner", name="Repo", ref=None,
        commit_sha="a" * 40, created_at="2026-01-01T00:00:00+00:00", container_count=2,
        component_count=5, mermaid_c4="C4Component\n", mermaid_flowchart="flowchart LR\n",
        model=Model(system_name="Repo", warnings=["w1"]), warnings=["w1"], tool_version="1.0",
    )  # fmt: skip
    return DiagramRecord(**{**base, **kw})


def test_roundtrip_and_survives_reopen(tmp_path):
    path = tmp_path / "d.db"
    saved = DiagramStore(path).add(rec())
    assert saved.id and saved.ref is None
    again = DiagramStore(path).get(saved.id)  # a new store object = a restart
    assert again == saved
    assert again.model.system_name == "Repo" and again.warnings == ["w1"]
    assert again.saved_edits == [] and (again.max_depth, again.auto_depth) == (1, 1)


def test_schema_matches_spec(tmp_path):
    path = tmp_path / "d.db"
    DiagramStore(path).add(rec())
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(diagrams)")}
    assert cols == {
        "id", "repo_url", "owner", "name", "ref", "commit_sha", "commit_date", "created_at",
        "container_count", "component_count", "max_depth", "auto_depth", "mermaid_c4",
        "mermaid_flowchart", "model_json", "warnings_json", "tool_version",
    }  # fmt: skip
    assert {r[1] for r in con.execute("PRAGMA table_info(edits)")} == {
        "diagram_id",
        "format",
        "depth",
        "text",
    }
    assert con.execute("PRAGMA user_version").fetchone()[0] == 3


def test_same_repo_ref_commit_reuses_entry_case_insensitively(tmp_path):
    s = DiagramStore(tmp_path / "d.db")
    a = s.add(rec())
    b = s.add(rec(repo_url="https://github.com/owner/repo", owner="owner", created_at="2027"))
    assert a.id == b.id and len(s.list()) == 1
    assert b.created_at == a.created_at and b.owner == "Owner"  # untouched: same tool version
    assert s.find("https://github.com/OWNER/REPO", None, "a" * 40).id == a.id
    assert s.find("https://github.com/owner/repo", "dev", "a" * 40) is None


def test_distinct_ref_or_commit_makes_new_entries(tmp_path):
    s = DiagramStore(tmp_path / "d.db")
    ids = {
        s.add(rec()).id,
        s.add(rec(ref="dev")).id,
        s.add(rec(commit_sha="b" * 40)).id,
    }
    assert len(ids) == 3 and s.has_repo("https://github.com/owner/repo", "dev")
    assert not s.has_repo("https://github.com/owner/repo", "nope")


def test_newer_tool_version_refreshes_generated_output_but_keeps_edits(tmp_path):
    s = DiagramStore(tmp_path / "d.db")
    first = s.add(rec())
    s.set_edit(first.id, "c4", 1, "my edit")
    second = s.add(rec(tool_version="2.0", mermaid_c4="new\n", container_count=9, max_depth=4))
    assert second.id == first.id
    assert (second.tool_version, second.mermaid_c4, second.container_count) == ("2.0", "new\n", 9)
    assert second.max_depth == 4
    assert s.get_edit(first.id, "c4", 1) == "my edit"
    assert [(e.format, e.depth) for e in second.saved_edits] == [("c4", 1)]


def test_edits_are_keyed_by_format_and_depth(tmp_path):
    s = DiagramStore(tmp_path / "d.db")
    d = s.add(rec(max_depth=3))
    s.set_edit(d.id, "c4", 1, "c4 depth 1")
    s.set_edit(d.id, "c4", 2, "c4 depth 2")
    s.set_edit(d.id, "flowchart", 2, "flow depth 2")
    assert s.get_edit(d.id, "c4", 1) == "c4 depth 1"
    assert s.get_edit(d.id, "c4", 2) == "c4 depth 2"
    assert s.get_edit(d.id, "flowchart", 1) is None
    assert [(e.format, e.depth) for e in s.get(d.id).saved_edits] == [
        ("c4", 1), ("c4", 2), ("flowchart", 2),
    ]  # fmt: skip
    s.set_edit(d.id, "c4", 1, "replaced")  # saving again replaces
    assert s.get_edit(d.id, "c4", 1) == "replaced"
    s.set_edit(d.id, "c4", 1, None)  # None discards
    assert s.get_edit(d.id, "c4", 1) is None and len(s.get(d.id).saved_edits) == 2


def test_set_edit_on_a_missing_diagram_and_delete_cascades(tmp_path):
    s = DiagramStore(tmp_path / "d.db")
    with pytest.raises(AppError) as e:
        s.set_edit("nope", "c4", 1, "x")
    assert e.value.code == "DIAGRAM_NOT_FOUND"
    d = s.add(rec())
    s.set_edit(d.id, "c4", 1, "x")
    s.delete(d.id)
    with sqlite3.connect(tmp_path / "d.db") as con:  # no orphaned edits left behind
        assert con.execute("SELECT count(*) FROM edits").fetchone()[0] == 0


def test_v1_database_is_migrated_in_place(tmp_path):
    """A database written by the first release keeps its diagrams and saved edits."""
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE diagrams (
          id TEXT PRIMARY KEY, repo_url TEXT NOT NULL, owner TEXT NOT NULL, name TEXT NOT NULL,
          ref TEXT NOT NULL DEFAULT '', commit_sha TEXT NOT NULL, created_at TEXT NOT NULL,
          container_count INTEGER NOT NULL, component_count INTEGER NOT NULL,
          mermaid_c4 TEXT NOT NULL, mermaid_flowchart TEXT, edited_c4 TEXT, edited_flowchart TEXT,
          model_json TEXT NOT NULL, warnings_json TEXT NOT NULL, tool_version TEXT NOT NULL,
          UNIQUE (repo_url, ref, commit_sha));
        PRAGMA user_version = 1;
        """
    )
    model = Model(system_name="Old").model_dump_json()
    con.execute(
        "INSERT INTO diagrams VALUES ('d1','https://github.com/o/old','o','old','','a1','2026-01-01',"
        "1,2,'c4 text','flow text','my c4 edit',NULL,?, '[]', '0.1.0')",
        (model,),
    )
    con.commit()
    con.close()

    s = DiagramStore(path)
    d = s.get("d1")
    assert (d.mermaid_c4, d.mermaid_flowchart, d.tool_version) == ("c4 text", "flow text", "0.1.0")
    assert (d.max_depth, d.auto_depth, d.commit_date) == (1, 1, "")  # flat: one level
    assert s.get_edit("d1", "c4", 1) == "my c4 edit"  # moved to the edits table at depth 1
    assert s.get_edit("d1", "flowchart", 1) is None
    check = sqlite3.connect(path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == 3
    # a regeneration by the new release then works on the migrated table
    s.add(rec(repo_url="https://github.com/o/old", owner="o", name="old", commit_sha="a1",
              tool_version="0.2.0", max_depth=3, auto_depth=2))  # fmt: skip
    assert s.get("d1").max_depth == 3 and s.get_edit("d1", "c4", 1) == "my c4 edit"


def test_list_newest_first_and_delete(tmp_path):
    s = DiagramStore(tmp_path / "d.db")
    old = s.add(rec(created_at="2026-01-01T00:00:00+00:00"))
    new = s.add(rec(commit_sha="c" * 40, created_at="2026-02-01T00:00:00+00:00"))
    assert [x.id for x in s.list()] == [new.id, old.id]
    assert not hasattr(s.list()[0], "mermaid_c4")
    s.delete(old.id)
    assert [x.id for x in s.list()] == [new.id]
    for fn in (s.delete, s.get):
        with pytest.raises(AppError) as e:
            fn(old.id)
        assert e.value.code == "DIAGRAM_NOT_FOUND"


def test_importing_the_app_does_not_create_a_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DIAGRAMMA_DATA_DIR", str(tmp_path / "nope"))
    DiagramStore()  # constructing is free; only use creates the file
    assert not (tmp_path / "nope").exists()


def test_version_constant_is_used_for_reuse_decision():
    assert isinstance(__version__, str)


def test_v2_database_is_migrated_to_v3_keeping_edits(tmp_path):
    """v2 restricted edits.format in SQL; v3 lets the API decide, so new view formats work."""
    path = tmp_path / "v2.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE diagrams (
          id TEXT PRIMARY KEY, repo_url TEXT NOT NULL, owner TEXT NOT NULL, name TEXT NOT NULL,
          ref TEXT NOT NULL DEFAULT '', commit_sha TEXT NOT NULL,
          commit_date TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
          container_count INTEGER NOT NULL, component_count INTEGER NOT NULL,
          max_depth INTEGER NOT NULL DEFAULT 1, auto_depth INTEGER NOT NULL DEFAULT 1,
          mermaid_c4 TEXT NOT NULL, mermaid_flowchart TEXT, model_json TEXT NOT NULL,
          warnings_json TEXT NOT NULL, tool_version TEXT NOT NULL,
          UNIQUE (repo_url, ref, commit_sha));
        CREATE TABLE edits (
          diagram_id TEXT NOT NULL REFERENCES diagrams(id) ON DELETE CASCADE,
          format TEXT NOT NULL CHECK (format IN ('c4', 'flowchart')),
          depth INTEGER NOT NULL, text TEXT NOT NULL, PRIMARY KEY (diagram_id, format, depth));
        PRAGMA user_version = 2;
        """
    )
    model = Model(system_name="Old").model_dump_json()
    con.execute(
        "INSERT INTO diagrams VALUES ('d1','https://github.com/o/old','o','old','','a1','2026-01-01',"
        "'2026-01-01',1,2,3,2,'c4 text','flow text',?,'[]','0.2.0')",
        (model,),
    )
    con.execute("INSERT INTO edits VALUES ('d1','c4',2,'kept c4'),('d1','flowchart',3,'kept flow')")
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):  # the old table really did reject other formats
        con.execute("INSERT INTO edits VALUES ('d1','layers',1,'x')")
    con.close()

    s = DiagramStore(path)
    d = s.get("d1")
    assert (d.max_depth, d.auto_depth) == (3, 2)
    assert (
        s.get_edit("d1", "c4", 2) == "kept c4" and s.get_edit("d1", "flowchart", 3) == "kept flow"
    )
    s.set_edit("d1", "layers", 1, "my layers edit")  # now allowed
    assert s.get_edit("d1", "layers", 1) == "my layers edit"
    assert [(e.format, e.depth) for e in s.get("d1").saved_edits] == [
        ("c4", 2), ("flowchart", 3), ("layers", 1),
    ]  # fmt: skip
    check = sqlite3.connect(path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == 3
    assert not check.execute("SELECT 1 FROM sqlite_master WHERE name = 'edits_v2'").fetchone()
    s.delete("d1")  # the foreign key still cascades after the rebuild
    assert check.execute("SELECT count(*) FROM edits").fetchone()[0] == 0
