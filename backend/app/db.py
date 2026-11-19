"""SQLite persistence for generated diagrams (SPEC §5.3).

One connection per operation (the API serves requests from a thread pool). The database file
and schema are created lazily on first use, so importing the app never touches the disk.
"""

import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from app.errors import AppError
from app.models import DiagramRecord, DiagramSummary, Model

DATA_DIR = Path(
    os.environ.get("DIAGRAMMA_DATA_DIR", Path.home() / ".local" / "share" / "diagramma")
)
SCHEMA_VERSION = 1
# Fixed column names, never user input.
EDIT_COLUMNS = {"c4": "edited_c4", "flowchart": "edited_flowchart"}

# `ref` is '' (not NULL) when no ref was given so that UNIQUE treats "no ref" as one value.
SCHEMA = """
CREATE TABLE IF NOT EXISTS diagrams (
  id TEXT PRIMARY KEY,
  repo_url TEXT NOT NULL,
  owner TEXT NOT NULL,
  name TEXT NOT NULL,
  ref TEXT NOT NULL DEFAULT '',
  commit_sha TEXT NOT NULL,
  created_at TEXT NOT NULL,
  container_count INTEGER NOT NULL,
  component_count INTEGER NOT NULL,
  mermaid_c4 TEXT NOT NULL,
  mermaid_flowchart TEXT,
  edited_c4 TEXT,
  edited_flowchart TEXT,
  model_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  tool_version TEXT NOT NULL,
  UNIQUE (repo_url, ref, commit_sha)
);
CREATE INDEX IF NOT EXISTS diagrams_created ON diagrams (created_at DESC);
"""

SUMMARY_COLS = (
    "id, repo_url, owner, name, ref, commit_sha, created_at, container_count, "
    "component_count, tool_version"
)


def _key(repo_url: str, ref: str | None) -> tuple[str, str]:
    # GitHub owner/repo names are case-insensitive: one identity per repo.
    return repo_url.lower(), ref or ""


class DiagramStore:
    def __init__(self, path: Path | str | None = None):
        self._explicit = Path(path) if path else None
        self._ready = False

    @property
    def _path(self) -> Path:
        if self._explicit:
            return self._explicit
        default = Path.home() / ".local" / "share" / "diagramma"
        return Path(os.environ.get("DIAGRAMMA_DATA_DIR", default)) / "diagramma.db"

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        if not self._ready:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            if not self._ready:
                with suppress(sqlite3.OperationalError):  # WAL needs a writable, local file
                    con.execute("PRAGMA journal_mode=WAL")
                con.executescript(SCHEMA)
                con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._ready = True
            with con:  # commit or roll back
                yield con
        finally:
            con.close()

    # -- mapping ----------------------------------------------------------------------------

    @staticmethod
    def _record(row: sqlite3.Row) -> DiagramRecord:
        return DiagramRecord(
            id=row["id"],
            repo_url=row["repo_url"],
            owner=row["owner"],
            name=row["name"],
            ref=row["ref"] or None,
            commit_sha=row["commit_sha"],
            created_at=row["created_at"],
            container_count=row["container_count"],
            component_count=row["component_count"],
            mermaid_c4=row["mermaid_c4"],
            mermaid_flowchart=row["mermaid_flowchart"],
            edited_c4=row["edited_c4"],
            edited_flowchart=row["edited_flowchart"],
            model=Model.model_validate_json(row["model_json"]),
            warnings=json.loads(row["warnings_json"]),
            tool_version=row["tool_version"],
        )

    # -- queries ----------------------------------------------------------------------------

    def get(self, diagram_id: str) -> DiagramRecord:
        with self._conn() as con:
            row = con.execute("SELECT * FROM diagrams WHERE id = ?", (diagram_id,)).fetchone()
        if row is None:
            raise AppError("DIAGRAM_NOT_FOUND", "Diagram not found.")
        return self._record(row)

    def find(self, repo_url: str, ref: str | None, commit_sha: str) -> DiagramRecord | None:
        url, r = _key(repo_url, ref)
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM diagrams WHERE repo_url = ? AND ref = ? AND commit_sha = ?",
                (url, r, commit_sha),
            ).fetchone()
        return self._record(row) if row else None

    def has_repo(self, repo_url: str, ref: str | None) -> bool:
        url, r = _key(repo_url, ref)
        with self._conn() as con:
            row = con.execute(
                "SELECT 1 FROM diagrams WHERE repo_url = ? AND ref = ? LIMIT 1", (url, r)
            ).fetchone()
        return row is not None

    def list(self) -> list[DiagramSummary]:
        with self._conn() as con:
            rows = con.execute(
                f"SELECT {SUMMARY_COLS} FROM diagrams ORDER BY created_at DESC, id"
            ).fetchall()
        return [DiagramSummary(**{**dict(r), "ref": r["ref"] or None}) for r in rows]

    # -- writes -----------------------------------------------------------------------------

    def add(self, record: DiagramRecord) -> DiagramRecord:
        """Insert, or reuse the entry for the same repo + ref + commit.

        An existing entry made by the same tool version is returned untouched. One made by an
        older version has its generated output refreshed; the user's saved edits are kept.
        """
        url, ref = _key(record.repo_url, record.ref)
        generated = (
            record.mermaid_c4,
            record.mermaid_flowchart,
            record.model.model_dump_json(),
            json.dumps(record.warnings),
            record.container_count,
            record.component_count,
            record.tool_version,
            record.created_at,
        )
        with self._conn() as con:
            row = con.execute(
                "SELECT id, tool_version FROM diagrams "
                "WHERE repo_url = ? AND ref = ? AND commit_sha = ?",
                (url, ref, record.commit_sha),
            ).fetchone()
            if row is not None:
                if row["tool_version"] != record.tool_version:
                    con.execute(
                        "UPDATE diagrams SET mermaid_c4=?, mermaid_flowchart=?, model_json=?, "
                        "warnings_json=?, container_count=?, component_count=?, tool_version=?, "
                        "created_at=? WHERE id=?",
                        (*generated, row["id"]),
                    )
                diagram_id = row["id"]
            else:
                diagram_id = uuid.uuid4().hex
                con.execute(
                    "INSERT INTO diagrams (id, repo_url, owner, name, ref, commit_sha, "
                    "mermaid_c4, mermaid_flowchart, model_json, warnings_json, container_count, "
                    "component_count, tool_version, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        diagram_id,
                        url,
                        record.owner,
                        record.name,
                        ref,
                        record.commit_sha,
                        *generated,
                    ),
                )
        return self.get(diagram_id)

    def set_edit(self, diagram_id: str, fmt: str, text: str | None) -> DiagramRecord:
        """Save (or with None, discard) the user's edited Mermaid text for one format.

        Text identical to the generated output is not an edit, so it is stored as none.
        """
        if fmt not in EDIT_COLUMNS:
            raise ValueError(f"unknown format {fmt!r}")
        record = self.get(diagram_id)
        generated = record.mermaid_c4 if fmt == "c4" else record.mermaid_flowchart
        if text == generated:
            text = None
        with self._conn() as con:
            con.execute(
                f"UPDATE diagrams SET {EDIT_COLUMNS[fmt]} = ? WHERE id = ?", (text, diagram_id)
            )
        return self.get(diagram_id)

    def delete(self, diagram_id: str) -> None:
        with self._conn() as con:
            n = con.execute("DELETE FROM diagrams WHERE id = ?", (diagram_id,)).rowcount
        if n == 0:
            raise AppError("DIAGRAM_NOT_FOUND", "Diagram not found.")
