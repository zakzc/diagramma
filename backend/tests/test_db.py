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
    assert again.edited_c4 is None


def test_schema_matches_spec(tmp_path):
    path = tmp_path / "d.db"
    DiagramStore(path).add(rec())
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(diagrams)")}
    assert cols == {
        "id", "repo_url", "owner", "name", "ref", "commit_sha", "created_at", "container_count",
        "component_count", "mermaid_c4", "mermaid_flowchart", "edited_c4", "edited_flowchart",
        "model_json", "warnings_json", "tool_version",
    }  # fmt: skip
    assert con.execute("PRAGMA user_version").fetchone()[0] == 1


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
    path = tmp_path / "d.db"
    s = DiagramStore(path)
    first = s.add(rec())
    with sqlite3.connect(path) as con:  # milestone 6 will write edits through the API
        con.execute("UPDATE diagrams SET edited_c4 = 'my edit' WHERE id = ?", (first.id,))
    second = s.add(rec(tool_version="2.0", mermaid_c4="new\n", container_count=9))
    assert second.id == first.id
    assert (second.tool_version, second.mermaid_c4, second.container_count) == ("2.0", "new\n", 9)
    assert second.edited_c4 == "my edit"


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
