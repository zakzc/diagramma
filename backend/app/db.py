"""SQLite persistence for generated diagrams (SPEC §5.3).

One connection per operation (the API serves requests from a thread pool). The database file
and schema are created lazily on first use, so importing the app never touches the disk.

Schema versions: 1 = one saved edit per format on the diagram row; 2 = edits live in their own
table keyed by (diagram, format, depth) and diagrams carry their depth range; 3 = the edits
table no longer restricts `format` in SQL (the API validates it), so new view formats such as
`layers` need no migration; 4 = `diagrams.source` ('github' or 'local', SPEC §5.6). Older
databases are migrated in place.
"""

import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from app.errors import AppError
from app.models import DiagramRecord, DiagramSummary, Model, SavedEdit

SCHEMA_VERSION = 4

# `ref` is '' (not NULL) when no ref was given so that UNIQUE treats "no ref" as one value.
SCHEMA = """
CREATE TABLE IF NOT EXISTS diagrams (
  id TEXT PRIMARY KEY,
  repo_url TEXT NOT NULL,
  owner TEXT NOT NULL,
  name TEXT NOT NULL,
  ref TEXT NOT NULL DEFAULT '',
  commit_sha TEXT NOT NULL,
  commit_date TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  container_count INTEGER NOT NULL,
  component_count INTEGER NOT NULL,
  max_depth INTEGER NOT NULL DEFAULT 1,
  auto_depth INTEGER NOT NULL DEFAULT 1,
  mermaid_c4 TEXT NOT NULL,
  mermaid_flowchart TEXT,
  model_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  tool_version TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'github',
  UNIQUE (repo_url, ref, commit_sha)
);
CREATE INDEX IF NOT EXISTS diagrams_created ON diagrams (created_at DESC);
CREATE TABLE IF NOT EXISTS edits (
  diagram_id TEXT NOT NULL REFERENCES diagrams(id) ON DELETE CASCADE,
  format TEXT NOT NULL,  -- validated by the API: c4, flowchart, layers
  depth INTEGER NOT NULL,
  text TEXT NOT NULL,
  PRIMARY KEY (diagram_id, format, depth)
);
"""

SUMMARY_COLS = (
    "id, repo_url, owner, name, ref, commit_sha, created_at, container_count, "
    "component_count, tool_version, source"
)


def _key(repo_url: str, ref: str | None) -> tuple[str, str]:
    # GitHub owner/repo names are case-insensitive: one identity per repo. Folder paths are not.
    return (repo_url if repo_url.startswith("file://") else repo_url.lower()), ref or ""


def _migrate_v1(con: sqlite3.Connection) -> None:
    """v1 -> v2: move the per-format edits into the edits table (they were flat, depth 1)."""
    for col, ddl in (
        ("commit_date", "TEXT NOT NULL DEFAULT ''"),
        ("max_depth", "INTEGER NOT NULL DEFAULT 1"),
        ("auto_depth", "INTEGER NOT NULL DEFAULT 1"),
    ):
        con.execute(f"ALTER TABLE diagrams ADD COLUMN {col} {ddl}")
    con.executescript(SCHEMA)  # creates the edits table
    for fmt, col in (("c4", "edited_c4"), ("flowchart", "edited_flowchart")):
        con.execute(
            "INSERT OR REPLACE INTO edits (diagram_id, format, depth, text) "
            f"SELECT id, ?, 1, {col} FROM diagrams WHERE {col} IS NOT NULL",
            (fmt,),
        )
        with suppress(sqlite3.OperationalError):  # DROP COLUMN needs SQLite >= 3.35
            con.execute(f"ALTER TABLE diagrams DROP COLUMN {col}")


def _migrate_v2(con: sqlite3.Connection) -> None:
    """v2 -> v3: rebuild `edits` without the CHECK on `format`, keeping every row."""
    con.execute("ALTER TABLE edits RENAME TO edits_v2")
    con.executescript(SCHEMA)  # creates the new edits table (diagrams already exists)
    con.execute(
        "INSERT INTO edits (diagram_id, format, depth, text) "
        "SELECT diagram_id, format, depth, text FROM edits_v2"
    )
    con.execute("DROP TABLE edits_v2")


def _migrate_v3(con: sqlite3.Connection) -> None:
    """v3 -> v4: record where a diagram came from; existing rows are GitHub diagrams."""
    con.execute("ALTER TABLE diagrams ADD COLUMN source TEXT NOT NULL DEFAULT 'github'")


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
            con.execute("PRAGMA foreign_keys = ON")
            if not self._ready:
                with suppress(sqlite3.OperationalError):  # WAL needs a writable, local file
                    con.execute("PRAGMA journal_mode=WAL")
                version = con.execute("PRAGMA user_version").fetchone()[0]
                has_table = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'diagrams'"
                ).fetchone()
                with con:
                    if has_table and version < 2:
                        _migrate_v1(con)  # also creates the current edits table
                    elif has_table and version == 2:
                        _migrate_v2(con)
                    else:
                        con.executescript(SCHEMA)
                    if has_table and version < 4:
                        _migrate_v3(con)
                    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._ready = True
            with con:  # commit or roll back
                yield con
        finally:
            con.close()

    # -- mapping ----------------------------------------------------------------------------

    def _record(self, con: sqlite3.Connection, row: sqlite3.Row) -> DiagramRecord:
        edits = con.execute(
            "SELECT format, depth FROM edits WHERE diagram_id = ? ORDER BY format, depth",
            (row["id"],),
        ).fetchall()
        return DiagramRecord(
            id=row["id"],
            repo_url=row["repo_url"],
            owner=row["owner"],
            name=row["name"],
            ref=row["ref"] or None,
            commit_sha=row["commit_sha"],
            commit_date=row["commit_date"],
            created_at=row["created_at"],
            container_count=row["container_count"],
            component_count=row["component_count"],
            max_depth=row["max_depth"],
            auto_depth=row["auto_depth"],
            mermaid_c4=row["mermaid_c4"],
            mermaid_flowchart=row["mermaid_flowchart"],
            saved_edits=[SavedEdit(format=e["format"], depth=e["depth"]) for e in edits],
            model=Model.model_validate_json(row["model_json"]),
            warnings=json.loads(row["warnings_json"]),
            tool_version=row["tool_version"],
            source=row["source"],
        )

    # -- queries ----------------------------------------------------------------------------

    def get(self, diagram_id: str) -> DiagramRecord:
        with self._conn() as con:
            row = con.execute("SELECT * FROM diagrams WHERE id = ?", (diagram_id,)).fetchone()
            if row is None:
                raise AppError("DIAGRAM_NOT_FOUND", "Diagram not found.")
            return self._record(con, row)

    def find(self, repo_url: str, ref: str | None, commit_sha: str) -> DiagramRecord | None:
        url, r = _key(repo_url, ref)
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM diagrams WHERE repo_url = ? AND ref = ? AND commit_sha = ?",
                (url, r, commit_sha),
            ).fetchone()
            return self._record(con, row) if row else None

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

    def get_edit(self, diagram_id: str, fmt: str, depth: int) -> str | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT text FROM edits WHERE diagram_id = ? AND format = ? AND depth = ?",
                (diagram_id, fmt, depth),
            ).fetchone()
        return row["text"] if row else None

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
            record.max_depth,
            record.auto_depth,
            record.commit_date,
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
                        "warnings_json=?, container_count=?, component_count=?, max_depth=?, "
                        "auto_depth=?, commit_date=?, tool_version=?, created_at=? WHERE id=?",
                        (*generated, row["id"]),
                    )
                diagram_id = row["id"]
            else:
                diagram_id = uuid.uuid4().hex
                con.execute(
                    "INSERT INTO diagrams (id, repo_url, owner, name, ref, commit_sha, "
                    "mermaid_c4, mermaid_flowchart, model_json, warnings_json, container_count, "
                    "component_count, max_depth, auto_depth, commit_date, tool_version, "
                    "created_at, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        diagram_id,
                        url,
                        record.owner,
                        record.name,
                        ref,
                        record.commit_sha,
                        *generated,
                        record.source,
                    ),
                )
        return self.get(diagram_id)

    def set_edit(self, diagram_id: str, fmt: str, depth: int, text: str | None) -> None:
        """Save (or with None, discard) the user's edited text for one format at one depth."""
        self.get(diagram_id)  # raises DIAGRAM_NOT_FOUND
        with self._conn() as con:
            if text is None:
                con.execute(
                    "DELETE FROM edits WHERE diagram_id = ? AND format = ? AND depth = ?",
                    (diagram_id, fmt, depth),
                )
            else:
                con.execute(
                    "INSERT OR REPLACE INTO edits (diagram_id, format, depth, text) "
                    "VALUES (?, ?, ?, ?)",
                    (diagram_id, fmt, depth, text),
                )

    def delete(self, diagram_id: str) -> None:
        with self._conn() as con:
            n = con.execute("DELETE FROM diagrams WHERE id = ?", (diagram_id,)).rowcount
        if n == 0:
            raise AppError("DIAGRAM_NOT_FOUND", "Diagram not found.")
