import shutil
from pathlib import Path

import pytest

from sharpit.engine.collectors.config.getenv_scan import GetenvFinding, scan_packages

CORPUS = Path(__file__).parent.parent.parent / "fixtures" / "getenv_corpus"


def test_corpus(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    shutil.copytree(CORPUS, root)
    pkg = root / "pkg"
    (pkg / "broken.py").write_text("def (:\n", encoding="utf-8")
    (pkg / "big.py").write_text('import os\nos.getenv("BIG")\n' + "#" * 1_100_000, encoding="utf-8")
    (pkg / "bad_bytes.py").write_bytes(b'import os\nos.getenv("BYTES")\n# \xff\xfe\n')
    (pkg / "deep.py").write_text("x = " + "+".join(["1"] * 200_000) + "\n", encoding="utf-8")
    (pkg / "deep2.py").write_text("x = " + "-" * 100_000 + "1\n", encoding="utf-8")
    for skipped in (".venv", "venv", "node_modules", "__pycache__", "site-packages"):
        (pkg / skipped).mkdir()
        (pkg / skipped / "m.py").write_text('import os\nos.getenv("SKIPPED")\n', encoding="utf-8")

    found = scan_packages([pkg])

    assert sorted(found, key=lambda f: f.key) == [
        GetenvFinding("BYTES", None, "pkg/bad_bytes.py:2"),
        GetenvFinding("FORM_A", "default-a", "pkg/forms.py:4"),
        GetenvFinding("FORM_B", None, "pkg/forms.py:5"),
        GetenvFinding("FORM_C", None, "pkg/forms.py:6"),
        GetenvFinding("FORM_D", "default-d", "pkg/forms.py:7"),
        GetenvFinding("FORM_E", None, "pkg/forms.py:8"),
        GetenvFinding("FORM_F", None, "pkg/forms.py:12"),
    ]


def test_keyword_default(tmp_path: Path) -> None:
    src = 'import os\nos.getenv("A", default="a")\nos.environ.get("B", default="b")\n'
    (tmp_path / "m.py").write_text(src, encoding="utf-8")
    found = scan_packages([tmp_path])
    assert [(f.key, f.default) for f in found] == [("A", "a"), ("B", "b")]


def test_unimported_names_not_matched(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text('environ.get("A")\ngetenv("B")\nfoo.getenv("C")\n', encoding="utf-8")
    assert scan_packages([tmp_path]) == []


def test_symlink_out_of_root_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "o.py").write_text('import os\nos.getenv("OUT")\n', encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
        (root / "flink.py").symlink_to(outside / "o.py")
    except OSError:
        pytest.skip("symlinks unavailable")
    assert scan_packages([root]) == []


def test_missing_root_is_empty(tmp_path: Path) -> None:
    assert scan_packages([tmp_path / "nope"]) == []
