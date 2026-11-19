from app.analysis.scan import scan_repo


def test_scan_ignores_and_classifies(tmp_path):
    def w(rel, text="a\nb\n"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    w("package.json", "{}")
    w("docker-compose.prod.yml", "")
    w("src/app.ts")
    w("src/ui/Button.tsx")
    w("src/app.test.ts")
    w("src/types.d.ts")
    w("src/vendor.min.js")
    w("pkg/main.py")
    w("pkg/test_main.py")
    w("pkg/conftest.py")
    w("pkg/api_pb2.py")
    w("node_modules/x/index.js")
    w("tests/unit.py")
    w("docs/conf.py")
    w(".hidden/x.py")
    w("cmd/main.go")
    w("README.md")
    w("big.js", "x" * 1_100_000)

    r = scan_repo(tmp_path)
    assert [f.path for f in r.files] == [
        "cmd/main.go",
        "pkg/main.py",
        "src/app.ts",
        "src/ui/Button.tsx",
    ]
    assert r.language_counts() == {"go": 1, "python": 1, "typescript": 2}
    assert r.manifests == ["docker-compose.prod.yml", "package.json"]
    assert r.skipped_large == 1
    assert next(f for f in r.files if f.path == "src/app.ts").loc == 2
    assert [f.supported for f in r.files] == [False, True, True, True]


def test_scan_is_deterministic(tmp_path):
    for n in ("b.py", "a.py", "c/d.py"):
        p = tmp_path / n
        p.parent.mkdir(exist_ok=True)
        p.write_text("x\n")
    assert scan_repo(tmp_path).files == scan_repo(tmp_path).files
