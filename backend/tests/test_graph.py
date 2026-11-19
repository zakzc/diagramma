from tests.helpers import model_of


def edges(m):
    return {(r.source, r.target): r for r in m.relations}


def test_js_import_forms_resolve(tmp_path):
    m = model_of(
        tmp_path,
        {
            "package.json": '{"name":"w","dependencies":{"react":"18"}}',
            "src/main.ts": (
                "import a from './ui/Button.js'\n"  # TS ESM style: .js -> .ts
                "import b from './store'\n"  # folder with index
                "export { c } from './api/c'\n"  # re-export
                "const d = require('./lib/d')\n"  # CommonJS
                "const e = await import('./pages/e')\n"  # dynamic import
                "import '@/hooks/h'\n"  # alias -> src/
                "import x from 'react'\n"  # third-party: ignored
            ),
            "src/ui/Button.ts": "x\n",
            "src/store/index.ts": "x\n",
            "src/api/c.ts": "x\n",
            "src/lib/d.js": "x\n",
            "src/pages/e.tsx": "x\n",
            "src/hooks/h.ts": "x\n",
        },
        "w",
    )
    targets = {t for (s, t) in edges(m) if s == "w_core"}
    assert targets == {"w_ui", "w_store", "w_api", "w_lib", "w_pages", "w_hooks"}


def test_python_import_forms_resolve(tmp_path):
    m = model_of(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "p"\n',
            "p/__init__.py": "",
            "p/main.py": (
                "import p.models.user\n"
                "from p.services import billing\n"  # `billing` is a submodule
                "from p import utils\n"  # from-import of a module
                "from .routes import r\n"  # relative
                "from . import cli_helpers\n"  # relative, bare
                "import os, json\n"  # stdlib: ignored
            ),
            "p/models/__init__.py": "",
            "p/models/user.py": "x\n",
            "p/services/__init__.py": "",
            "p/services/billing.py": "x\n",
            "p/utils/__init__.py": "",
            "p/utils/strings.py": "x\n",
            "p/routes/__init__.py": "",
            "p/routes/r.py": "from ..models import user\n",
            "p/cli_helpers.py": "x\n",
        },
        "p",
    )
    e = edges(m)
    assert {t for (s, t) in e if s == "p_core"} == {"p_models", "p_services", "p_utils", "p_routes"}
    assert ("p_routes", "p_models") in e  # `from ..models import user`


def test_import_counts_become_strength_and_self_edges_are_dropped(tmp_path):
    m = model_of(
        tmp_path,
        {
            "package.json": '{"name":"w"}',
            "src/a/x.ts": "import './y'\nimport '../b/p'\n",
            "src/a/y.ts": "import '../b/q'\n",
            "src/b/p.ts": "x\n",
            "src/b/q.ts": "x\n",
        },
        "w",
    )
    assert [(r.source, r.target, r.strength) for r in m.relations] == [("w_a", "w_b", 2)]


def test_import_evidence_creates_external_without_manifest_dependency(tmp_path):
    m = model_of(
        tmp_path,
        {
            "package.json": '{"name":"w"}',  # hoisted deps: nothing declared
            "src/db/client.ts": (
                "import { Pool } from 'pg'\nimport r from '@aws-sdk/client-s3/commands'\n"
            ),
        },
        "w",
    )
    assert {e.id for e in m.externals} == {"postgres", "s3"}
    assert ("w_db", "postgres") in edges(m)
    assert any("import of 'pg'" in ev for ev in m.externals[1].evidence + m.externals[0].evidence)


def test_syntax_errors_do_not_break_analysis(tmp_path):
    m = model_of(
        tmp_path,
        {"package.json": '{"name":"w"}', "src/a/x.ts": "import ((( from\n", "src/b/y.ts": "x\n"},
        "w",
    )
    assert len(m.containers[0].components) == 2
