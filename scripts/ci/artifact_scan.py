"""Scan CI artifacts for planted canary values before upload (B8).

A public scanner that runs before every actions/upload-artifact step in CI. Fails naming the file,
line, and form (raw, URL-encoded, JSON-escaped, base64) of any hit. Prints values never, only their
index. With no values file, prints "no planted values in this job" and passes unless --require.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple


class Hit(NamedTuple):
    path: Path
    line: int
    form: str
    value_index: int

    @property
    def file(self) -> Path:
        return self.path


def _load_values(
    values: Sequence[str] | None,
    values_file: Path | str | None,
) -> list[str]:
    if values is not None:
        return [v.strip() for v in values if v.strip()]
    if values_file is None:
        return []
    v_path = Path(os.path.expandvars(str(values_file)))
    if not v_path.is_file():
        return []
    return [line.strip() for line in v_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]


def _resolve_target_files(paths: Sequence[Path | str] | Path | str) -> list[Path]:
    target_paths = [paths] if isinstance(paths, (str, Path)) else list(paths)
    files: list[Path] = []
    for p in target_paths:
        resolved = Path(os.path.expandvars(str(p)))
        if resolved.is_file():
            files.append(resolved)
        elif resolved.is_dir():
            files.extend(f for f in sorted(resolved.rglob("*")) if f.is_file())
    return files


def _forms_for_value(raw_val: str) -> dict[str, list[str]]:
    raw = raw_val
    url = urllib.parse.quote(raw_val)
    url_plus = urllib.parse.quote_plus(raw_val)
    json_esc = json.dumps(raw_val)[1:-1]
    json_full = json.dumps(raw_val)
    b64 = base64.b64encode(raw_val.encode("utf-8")).decode("ascii")
    b64_unpadded = b64.rstrip("=")
    urlsafe = base64.urlsafe_b64encode(raw_val.encode("utf-8")).decode("ascii")
    urlsafe_unpadded = urlsafe.rstrip("=")

    forms: dict[str, list[str]] = {
        "base64": [s for s in (b64, b64_unpadded, urlsafe, urlsafe_unpadded) if s],
        "JSON-escaped": [s for s in (json_esc, json_full) if s and s != raw],
        "URL-encoded": [s for s in (url, url_plus) if s and s != raw],
        "raw": [raw],
    }
    return forms


def _scan_lines(
    file_path: Path,
    lines: list[str],
    v_idx: int,
    forms: dict[str, list[str]],
) -> list[Hit]:
    hits: list[Hit] = []
    for line_no, line in enumerate(lines, 1):
        for form_name, candidates in forms.items():
            if any(cand in line for cand in candidates):
                hits.append(Hit(file_path, line_no, form_name, v_idx))
    return hits


def scan(
    paths: Sequence[Path | str] | Path | str,
    values: Sequence[str] | None = None,
    *,
    values_file: Path | str | None = None,
) -> list[Hit]:
    """Scan given paths for planted canary values in any of four forms."""
    normalized_values = _load_values(values, values_file)
    if not normalized_values:
        return []

    files_to_scan = _resolve_target_files(paths)
    value_forms = [(idx, _forms_for_value(v)) for idx, v in enumerate(normalized_values)]

    hits: list[Hit] = []
    for file_path in files_to_scan:
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for v_idx, forms in value_forms:
            hits.extend(_scan_lines(file_path, lines, v_idx, forms))

    return list(dict.fromkeys(hits))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan artifacts for planted canary values.")
    parser.add_argument("--values-file", help="Path to canary values file (one per line).")
    parser.add_argument("--require", action="store_true", help="Fail if values file is missing or empty.")
    parser.add_argument("files", nargs="*", help="Files or directories to scan.")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    values_file_arg = args.values_file or os.environ.get("SHARPIT_CANARY_FILE")
    if not values_file_arg:
        if args.require:
            print("artifact_scan: --require set but no values file provided", file=sys.stderr)
            return 1
        print("no planted values in this job")
        return 0

    values_path = Path(os.path.expandvars(values_file_arg))
    if not values_path.is_file():
        if args.require:
            print(f"artifact_scan: --require set but values file not found: {values_file_arg}", file=sys.stderr)
            return 1
        print("no planted values in this job")
        return 0

    raw_lines = values_path.read_text(encoding="utf-8", errors="replace").splitlines()
    values = [line.strip() for line in raw_lines if line.strip()]
    if not values:
        if args.require:
            print(f"artifact_scan: --require set but values file is empty: {values_file_arg}", file=sys.stderr)
            return 1
        print("no planted values in this job")
        return 0

    hits = scan(args.files, values)
    if hits:
        for h in hits:
            print(
                f"artifact_scan: planted value hit in {h.path}:{h.line} form={h.form} value_index={h.value_index}",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
