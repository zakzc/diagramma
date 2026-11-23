"""Classify a React JS/TS file for the Imports view (SPEC §9.4). Heuristics on path, name and
content; the first matching rule wins. Never executes code."""

import posixpath
import re
from dataclasses import dataclass

from app.models import FileKind

REACT_PACKAGES = {"react", "react-dom", "react-native", "next", "preact"}
# npm packages that talk to a server: drawn as external API nodes and mark the importer as `api`.
API_PACKAGES = {
    "axios", "ky", "got", "superagent", "node-fetch", "cross-fetch", "isomorphic-fetch",
    "swr", "@tanstack/react-query", "react-query", "@apollo/client", "urql", "graphql-request",
    "@trpc/client", "@trpc/react-query", "socket.io-client", "ws", "openapi-fetch",
}  # fmt: skip
STATE_PACKAGES = {
    "zustand", "jotai", "recoil", "valtio", "mobx", "@reduxjs/toolkit", "redux", "redux-saga",
    "xstate", "nanostores", "@tanstack/store",
}  # fmt: skip

_ENTRY = re.compile(
    r"\b(createRoot|hydrateRoot)\s*\(|ReactDOM\.(render|hydrate)\s*\(|registerRootComponent\s*\("
    r"|AppRegistry\.registerComponent\s*\("
)
_HOOK_EXPORT = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function\*?\s+|const\s+|let\s+|var\s+)?use[A-Z0-9_]"
    r"|\bexport\s*\{[^}]*\buse[A-Z0-9_]"
)
_STATE = re.compile(
    r"\b(createContext|createSlice|configureStore|createStore|createReducer|createAtom)\s*[<(]"
)
_NETWORK = re.compile(r"(?<![.\w])fetch\s*\(|\bXMLHttpRequest\b|\bnew\s+WebSocket\s*\(")
_API_ROUTE = re.compile(r"(^|/)pages/api/|(^|/)app/(.+/)?route\.[tj]sx?$")
_NEXT_PAGE = re.compile(r"(^|/)app/(.+/)?(page|layout|template|loading|error|not-found)\.[tj]sx?$")
_API_NAME = re.compile(r"(api|service|services|client|queries|mutations)$", re.I)
_CONFIG_NAME = re.compile(r"(^|[._-])(config|constants|settings|env)$", re.I)

PAGE_DIRS = {"pages", "routes", "screens", "views"}
API_DIRS = {
    "api", "apis", "services", "service", "clients", "client", "requests", "http", "graphql",
    "trpc",
}  # fmt: skip
DB_DIRS = {"db", "database", "prisma", "drizzle", "migrations", "repositories", "dao"}
TYPES_DIRS = {"types", "typings", "interfaces"}
CONFIG_DIRS = {"config", "configs", "constants"}


@dataclass(frozen=True)
class Evidence:
    path: str  # posix, relative to the repo
    text: str
    has_jsx: bool
    packages: set[str]  # bare npm package names imported
    db_external: bool = False  # imports a catalogue database
    service_external: bool = False  # imports a catalogue third-party service or queue


def display_name(path: str) -> str:
    base = posixpath.splitext(posixpath.basename(path))[0]
    if base == "index":
        parent = posixpath.basename(posixpath.dirname(path))
        return parent or base
    return base


def classify(e: Evidence) -> FileKind:
    dirs = {d.lower() for d in posixpath.dirname(e.path).split("/") if d}
    base = posixpath.splitext(posixpath.basename(e.path))[0]
    low = base.lower()

    if _ENTRY.search(e.text):
        return "entry"
    if _API_ROUTE.search(e.path):
        return "api"
    if e.has_jsx and (_NEXT_PAGE.search(e.path) or (dirs & PAGE_DIRS)):
        return "page"
    if _STATE.search(e.text) or (not e.has_jsx and e.packages & STATE_PACKAGES):
        return "state"
    if _HOOK_EXPORT.search(e.text) and (not e.has_jsx or re.match(r"use[A-Z0-9]", base)):
        return "hook"
    if e.has_jsx:
        return "component"
    if (
        low in {"types", "interfaces", "typings"}
        or low.endswith((".types", ".type"))
        or dirs & TYPES_DIRS
    ):
        return "types"
    if e.db_external or dirs & DB_DIRS:
        return "db"
    if (
        e.packages & API_PACKAGES
        or e.service_external
        or _NETWORK.search(e.text)
        or dirs & API_DIRS
        or _API_NAME.search(base)
    ):
        return "api"
    if _CONFIG_NAME.search(base) or dirs & CONFIG_DIRS:
        return "config"
    return "util"
