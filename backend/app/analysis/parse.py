"""Import extraction with tree-sitter (SPEC §6, §8). Static only; never executes code."""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from tree_sitter import Node
from tree_sitter_language_pack import get_parser


@dataclass(frozen=True)
class ImportRef:
    module: str  # "./a/b", "@scope/pkg", "app.models", "" for `from . import x`
    level: int = 0  # Python relative-import dots
    names: tuple[str, ...] = ()  # Python `from m import a, b`


@cache
def _parser(grammar: str) -> Any:
    return get_parser(grammar)  # type: ignore[arg-type]


def grammar_for(path: str, language: str) -> str:
    if language == "python":
        return "python"
    if path.endswith(".tsx"):
        return "tsx"
    return "typescript" if language == "typescript" else "javascript"


def _walk(root: Node) -> Iterator[Node]:
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def _text(n: Node | None) -> str:
    return n.text.decode("utf-8", "replace") if n is not None and n.text is not None else ""


def _js_string(n: Node | None) -> str | None:
    if n is None or n.type != "string":
        return None
    return _text(n)[1:-1]


def _js_imports(root: Node) -> list[ImportRef]:
    out: list[ImportRef] = []
    for n in _walk(root):
        spec: str | None = None
        if n.type in ("import_statement", "export_statement"):
            spec = _js_string(n.child_by_field_name("source"))
        elif n.type == "call_expression":
            fn = n.child_by_field_name("function")
            args = n.child_by_field_name("arguments")
            if fn is not None and _text(fn) in ("require", "import") and args is not None:
                first = next((c for c in args.named_children), None)
                spec = _js_string(first)
        if spec:
            out.append(ImportRef(spec))
    return out


def _dotted(n: Node) -> str:
    if n.type == "aliased_import":
        n = n.child_by_field_name("name") or n
    return _text(n)


def _py_imports(root: Node) -> list[ImportRef]:
    out: list[ImportRef] = []
    for n in _walk(root):
        if n.type == "import_statement":
            out += [ImportRef(_dotted(c)) for c in n.children_by_field_name("name")]
        elif n.type == "import_from_statement":
            mod = n.child_by_field_name("module_name")
            level, module = 0, ""
            if mod is not None and mod.type == "relative_import":
                prefix = next((c for c in mod.children if c.type == "import_prefix"), None)
                level = _text(prefix).count(".")
                module = "".join(_text(c) for c in mod.children if c.type == "dotted_name")
            elif mod is not None:
                module = _text(mod)
            names = tuple(_dotted(c) for c in n.children_by_field_name("name"))
            out.append(ImportRef(module, level, names))
    return out


def extract_imports(path: Path, rel_path: str, language: str) -> list[ImportRef]:
    """Imports of one file; a file that cannot be read yields no imports."""
    try:
        source = path.read_bytes()
    except OSError:
        return []
    root = _parser(grammar_for(rel_path, language)).parse(source).root_node
    return _py_imports(root) if language == "python" else _js_imports(root)


_JSX_NODES = {"jsx_element", "jsx_self_closing_element", "jsx_fragment"}


@dataclass(frozen=True)
class JsFile:
    imports: list[ImportRef]
    has_jsx: bool
    text: str


def read_js_file(path: Path, rel_path: str, language: str) -> JsFile:
    """Imports, whether the file contains JSX, and its source text (for the Imports view)."""
    try:
        source = path.read_bytes()
    except OSError:
        return JsFile([], False, "")
    root = _parser(grammar_for(rel_path, language)).parse(source).root_node
    has_jsx = any(n.type in _JSX_NODES for n in _walk(root))
    return JsFile(_js_imports(root), has_jsx, source.decode("utf-8", "replace"))
