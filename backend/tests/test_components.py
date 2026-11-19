from tests.helpers import model_of


def comps(m, container_id, depth=1):
    """Components of one level, by name (level 1 = the top-level folders)."""
    c = next(c for c in m.containers if c.id == container_id)
    return {k.name: k for k in c.components if k.depth == depth}


def test_feature_folders_roles_and_core(tmp_path):
    m = model_of(
        tmp_path,
        {
            "package.json": '{"name":"app","dependencies":{"express":"4"}}',
            "src/index.ts": "x\n",
            "src/routes/users.ts": "x\n",
            "src/services/user_service.ts": "x\n",
            "src/repositories/users.ts": "x\n",
            "src/models/user.ts": "x\n",
            "src/billing-engine/index.ts": "x\n",
            "src/utils/log.ts": "x\n",
            "scripts/seed.ts": "x\n",
        },
        "app",
    )
    k = comps(m, "app")
    assert {n: c.role for n, c in k.items()} == {
        "Core": "other",  # src/index.ts + files outside src/ (scripts/seed.ts)
        "Routes": "controller",
        "Services": "service",
        "Repositories": "repository",
        "Models": "model",
        "Billing Engine": "other",
        "Utils": "util",
    }
    assert k["Core"].weight >= 1 and k["Routes"].paths == ["src/routes"]
    assert any("folder src/routes" in e for e in k["Routes"].evidence)


def test_python_package_without_src_folder(tmp_path):
    m = model_of(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "mylib"\n',
            "mylib/__init__.py": "",
            "mylib/api/x.py": "x\n",
            "mylib/db/y.py": "x\n",
            "mylib/cli.py": "x\n",
            "setup_helpers.py": "x\n",
        },
        "mylib",
    )
    assert set(comps(m, "mylib")) == {"Core", "API", "DB"}


def test_lone_wrapper_package_is_descended(tmp_path):
    m = model_of(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "p"\n',
            "src/pkg/__init__.py": "",
            "src/pkg/web/a.py": "x\n",
            "src/pkg/store/b.py": "x\n",
        },
    )
    assert set(comps(m, "p")) == {"Web", "Store"}


def test_core_name_clash_and_views_role(tmp_path):
    m = model_of(
        tmp_path,
        {
            "requirements.txt": "django\n",
            "app/main.py": "x\n",
            "app/core/settings.py": "x\n",
            "app/views/a.py": "x\n",
        },
        "dj",
    )
    k = comps(m, "dj")
    assert set(k) == {"Main", "Core", "Views"} and k["Views"].role == "controller"


def test_unsupported_language_still_gets_components(tmp_path):
    m = model_of(
        tmp_path, {"cmd/main.go": "x\n", "internal/db/a.go": "x\n", "internal/web/b.go": "x\n"}
    )
    assert len(m.containers) == 1 and m.containers[0].components
    assert any("Unsupported language" in w for w in m.warnings)
    assert m.relations == []  # no import analysis for Go in the MVP
