import pytest

from app.errors import AppError
from app.render.c4 import RenderMeta
from app.render.imports import analyze_imports, render_imports
from tests.helpers import model_of

META = RenderMeta("o/w", "main", "c" * 40, "2026-01-02T03:04:05+00:00", "0.4.0")

REACT_APP = {
    "package.json": '{"name":"shop","dependencies":{"react":"18","axios":"1","mongoose":"8",'
    '"react-router-dom":"6"}}',
    "src/main.tsx": (
        "import { createRoot } from 'react-dom/client'\nimport App from './App'\n"
        "createRoot(document.getElementById('root')!).render(<App />)\n"
    ),
    "src/App.tsx": (
        "import React from 'react'\nimport Home from './pages/Home'\n"
        "export default function App() { return <Home /> }\n"
    ),
    "src/pages/Home.tsx": (
        "import { useCart } from '../hooks/useCart'\nimport Button from '../components/Button'\n"
        "export default function Home() { const c = useCart(); return <Button/> }\n"
    ),
    "src/components/Button.tsx": "export default function Button() { return <button/> }\n",
    "src/hooks/useCart.ts": (
        "import { useContext } from 'react'\nimport { CartContext } from '../state/cart'\n"
        "import { getCart } from '../api/cart'\n"
        "export function useCart() { getCart(); return useContext(CartContext) }\n"
    ),
    "src/state/cart.ts": (
        "import { createContext } from 'react'\nexport const CartContext = createContext(null)\n"
    ),
    "src/api/cart.ts": (
        "import axios from 'axios'\nexport const getCart = () => axios.get('/cart')\n"
    ),
    "src/db/client.ts": "import mongoose from 'mongoose'\nexport default mongoose\n",
    "src/lib/format.ts": "export const fmt = (n: number) => String(n)\n",
    "src/lib/unused.ts": "export const x = 1\n",
}


def kinds(tmp_path, files=REACT_APP):
    m = model_of(tmp_path, files, "shop")
    return m, {f.path: f.kind for f in m.files}


def test_files_are_classified_by_what_they_are(tmp_path):
    _, k = kinds(tmp_path)
    assert k["src/main.tsx"] == "entry"
    assert k["src/pages/Home.tsx"] == "page"
    assert k["src/App.tsx"] == "component" and k["src/components/Button.tsx"] == "component"
    assert k["src/hooks/useCart.ts"] == "hook"
    assert k["src/state/cart.ts"] == "state"
    assert k["src/api/cart.ts"] == "api"
    assert k["src/db/client.ts"] == "db"
    assert k["src/lib/format.ts"] == "util"


def test_diagram_has_colours_shapes_and_edges(tmp_path):
    m, _ = kinds(tmp_path)
    text = render_imports(m, META)
    assert text.startswith("flowchart LR\n")
    assert "classDef hook fill:#CBEFD3" in text and "classDef db fill:#FFC9C0" in text
    assert 'f_src_hooks_useCart_ts(["useCart"])' in text  # hook = stadium
    assert 'f_src_state_cart_ts{{"cart"}}' in text  # state = hexagon
    assert 'f_src_db_client_ts[("client")]' in text  # database access = cylinder
    assert 'subgraph grp_hooks["hooks"]' in text
    edges = [ln.strip() for ln in text.splitlines() if "-->" in ln]
    assert "f_src_pages_Home_tsx --> f_src_hooks_useCart_ts" in edges
    assert "f_src_api_cart_ts --> pkg_axios" in edges  # API client package drawn as a node
    assert "f_src_db_client_ts --> mongodb" in edges  # database
    assert "class pkg_axios ext_api" in text and "class mongodb ext_db" in text
    a = analyze_imports(m)
    assert a.summary.isolated == 2
    assert {i.kind for i in a.summary.legend} >= {"entry", "page", "component", "hook", "ext_db"}


def test_is_deterministic(tmp_path):
    m, _ = kinds(tmp_path)
    assert render_imports(m, META) == render_imports(m, META)


def test_non_react_repo_is_not_available(tmp_path):
    m = model_of(tmp_path, {"package.json": '{"name":"x"}', "src/a.ts": "export const a = 1\n"})
    with pytest.raises(AppError) as e:
        analyze_imports(m)
    assert e.value.code == "IMPORTS_UNAVAILABLE"


def test_backend_container_next_to_a_react_one_is_left_out(tmp_path):
    files = {
        "web/package.json": '{"name":"web","dependencies":{"react":"18"}}',
        "web/src/App.tsx": "import { f } from './f'\nexport default () => <div/>\n",
        "web/src/f.ts": "export const f = 1\n",
        "api/package.json": '{"name":"api","dependencies":{"express":"4"}}',
        "api/src/server.ts": "import { h } from './h'\nexport const s = h\n",
        "api/src/h.ts": "export const h = 1\n",
    }
    m, k = kinds(tmp_path, files)
    assert set(k) == {"web/src/App.tsx", "web/src/f.ts"}


def test_a_file_imported_by_much_of_the_app_is_drawn_once_with_a_count(tmp_path):
    files = {"package.json": '{"name":"x","dependencies":{"react":"18"}}'}
    files["src/lib/cn.ts"] = "export const cn = () => ''\n"
    for i in range(10):
        files[f"src/ui/C{i}.tsx"] = (
            f"import {{ cn }} from '../lib/cn'\nexport const C{i} = () => <i/>\n"
        )
    m = model_of(tmp_path, files, "x")
    a = analyze_imports(m)
    assert a.summary.hubs == 1 and a.summary.hub_edges_omitted == 10 and a.summary.edges_drawn == 0
    text = render_imports(m, META)
    assert 'used by 10"]' in text and "--> f_src_lib_cn_ts" not in text
    assert "class f_src_lib_cn_ts hub" in text


def test_names_are_made_safe_for_mermaid(tmp_path):
    files = {
        "package.json": '{"name":"x","dependencies":{"react":"18"}}',
        "src/a.tsx": "import './b {x}'\nexport const A = () => <i/>\n",
        "src/b {x}.tsx": "export const B = () => <i/>\n",
    }
    text = render_imports(model_of(tmp_path, files, "x"), META)
    assert "{x}" not in text.replace("{{", "").replace("}}", "") and text.count('"') % 2 == 0


def test_golden_file(tmp_path):
    """Expected text; the frontend also parses it with the pinned Mermaid."""
    from pathlib import Path

    path = Path(__file__).parent / "golden" / "react_imports.mmd"
    text = render_imports(model_of(tmp_path, REACT_APP, "shop"), META)
    if not path.exists():
        path.write_text(text)
    assert text == path.read_text()
