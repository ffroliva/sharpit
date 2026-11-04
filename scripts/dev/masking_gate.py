"""The pinned-tree differential gates of the output masking redesign (spec §1, A2 and A7).

    uv run python scripts/dev/masking_gate.py a2 --rows 60000 --seed 11 --candidate HEAD
    uv run python scripts/dev/masking_gate.py a7 --rows 200000 --seed 11 --candidate HEAD

Each tree is exported with ``git archive`` into a temporary directory and driven by a subprocess that asserts the
``sharpit`` it imported is that tree's, so a label can never name one tree and run another. Nothing is written outside
the temporary directory. The corpus is ``p2_gen``'s (``probe8/gen.py``): text with planted secrets, some of it wrapped
in the shapes of a driver error.

* **A2:** a secret the baseline (``v0.4.0``) hid on a surface stays hidden on that surface. The baseline is what 0.4.0
  ran there: ``_sql_message`` for traces, ``mask_text`` for logs, exceptions and collectors, the recorder for the
  recorder, ``_sql_attribute`` for ``db.statement``. The old ``p2_cmp`` used ``mask_text`` for traces and hid 2,270
  regressions. Target 0.
* **A7:** ``mask_text`` on text with no SQL block is byte-identical to the baseline (``fa2d51e``), or hides more: 0
  secrets newly shown.
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import random
import string
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WINDOW = 8  # a substring of a long secret counts (spec A2 r2, r3): every window of 8, stepping by 1
BASELINES = {"a2": "v0.4.0", "a7": "fa2d51e"}
A2_SURFACES = ("text_off", "text_on", "err_off", "err_on", "err_mysql", "rec_off", "rec_on", "trace", "statement")
A7_SURFACES = ("text_off", "text_on")
# the corpus's own fixed text: a window made of it is no part of a secret, whatever a masker does with the rest
FIXED = (
    "postgres://user:", "@db.host/x", "redis://:", "@h:6379/0", "https://", "@sentry.io/1", "https://api.x.io/p?token=",
    "https://api.x.io/", "?password=", "/x?api_key=", "/reset/", "Server=x;Password=", "AccountKey=", "sk_live_",
    "glpat-", "xoxb-", "AKIA", "ghp_", "eyJ",
)  # fmt: skip

# --- the corpus -----------------------------------------------------------------------------------------------------

_SENSITIVE = ("password", "pwd", "token", "api_key", "secret", "Authorization", "Cookie", "set-cookie", "x-api-key",
              "private_key", "session_id", "DB_PASS", "client_secret", "auth", "pgpass", "passwd", "credentials",
              "apikey", "my.secret.key", "X-Api-Key")  # fmt: skip
_PLAIN = ("user", "host", "a", "msg", "https", "note", "id", "url", "dsn", "x", "name", "v")
_GLUE = (" ", " ", ", ", "\n", "\n", ":", "=", ",", ";", "&", "?", "/", ', "', " {", "(", "[", "", "', '", " | ", "\\n",
         "\t", ": ", "@")  # fmt: skip
_QUIET = ("connection refused", "user=bob", "id: 42", "host=db", "ok", "a b c", "Token expired", "note:")
_PEM = "-----{} PRIVATE KEY-----"


class _Generator:
    """``probe8/gen.py`` as a class: the same seed draws the same rows, so the RCA's counts can be reproduced."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.wrapped = "plain"

    def rnd(self, n: int = 20) -> str:
        return "".join(self.rng.choices(string.ascii_letters + string.digits, k=n))

    def upper(self, n: int) -> str:
        return "".join(self.rng.choices(string.ascii_uppercase + string.digits, k=n))

    def jwt(self) -> str:
        return f"eyJ{self.rnd(14)}.{self.rnd(14)}.{self.rnd(14)}".replace("+", "")

    def shapes(self) -> list[Callable[[], str]]:
        r = self.rnd
        return [
            lambda: r(), lambda: r().lower(), lambda: "AKIA" + self.upper(16), lambda: "ghp_" + r(24),
            lambda: "sk_live_" + r(24), lambda: "glpat-" + r(22), lambda: "xoxb-" + r(22), self.jwt,
            lambda: f"postgres://user:{r()}@db.host/x", lambda: f"redis://:{r()}@h:6379/0",
            lambda: f"https://{r()}@sentry.io/1", lambda: f"https://api.x.io/p?token={r()}",
            lambda: f"https://api.x.io/{r()}?password={r()}",
            lambda: f"https://api.x.io/{'ghp_' + r(24)}/x?api_key={r()}",
            lambda: f"/reset/{self.jwt()}", lambda: f"Server=x;Password={r()}", lambda: f"AccountKey={r()}",
        ]  # fmt: skip

    def value(self) -> tuple[list[str], str]:
        s, t = self.rnd(), self.rnd()
        shape = self.rng.choice(self.shapes())()
        begin, end = _PEM.format("BEGIN"), _PEM.format("END")
        forms: list[tuple[list[str], str]] = [
            ([s], s), ([s], f'"{s}"'), ([s], f"'{s}'"), ([s, t], f'"{s} {t}"'), ([s, t], f"'{s} {t}'"),
            ([s, t], f'"{s}\n{t}"'), ([s, t], f"'{s}\n{t}'"), ([s, t], f'"{s}\r\n{t}"'), ([s, t], f'"\n{s}\n{t}\n"'),
            ([s, t], f"[{s}, {t}]"), ([s, t], f"({s}, {t})"), ([s, t], f'"{s}\\"{t}"'), ([s, t], f"'{s}\\'{t}'"),
            ([s, t], f'"{s}\\n{t}"'), ([s], f"Bearer {s}"), ([s], f"Basic {s}"), ([s], f"Token {s}"),
            ([s, t], f"{s};{t}"), ([s, t], f"{s},{t}"), ([s, t], f"{s}&{t}"), ([s, t], "{" + f"{s}: {t}" + "}"),
            ([s, t], f"{s} {t}"), ([s, t], f"'{begin}\n{s}\n{t}\n{end}\n'"),
            ([s, t], f'"{begin.replace("BEGIN ", "BEGIN RSA ")}\n{s}\n{t}\n{end.replace("END ", "END RSA ")}"'),
            ([shape], shape), ([shape], f'"{shape}"'), ([shape], f"'{shape}'"),
        ]  # fmt: skip
        return self.rng.choice(forms)

    def fragment(self) -> tuple[list[str], str]:
        kind = self.rng.random()
        if kind < 0.55:
            key = self.rng.choice(_SENSITIVE if self.rng.random() < 0.8 else _PLAIN)
            q = self.rng.choice(["", "", '"', "'"])
            sep = self.rng.choice(["=", ": ", ":", " = ", " : ", "=\n", ":\n  "])
            secrets, val = self.value()
            return secrets, f"{q}{key}{q}{sep}{val}"
        if kind < 0.8:
            s = self.rng.choice(self.shapes())()
            return [s], s
        if kind < 0.9:
            s = self.rng.choice(self.shapes())()
            return [s], self.rng.choice([f"Bearer {s}", f"curl -H 'Authorization: Bearer {s}'", f"GET /x/{s} HTTP/1.1",
                                         f"failed for {s}."])  # fmt: skip
        return [], self.rng.choice(_QUIET)

    def wrap(self, text: str) -> tuple[str, str | None]:
        r = self.rng.random()
        if r < 0.55:
            self.wrapped = "plain"
            return text, None
        if r < 0.7:
            sql = "SELECT * FROM t WHERE a = 1"
            self.wrapped = "driver_then_real_sql"
            return f"(psycopg2.errors.UniqueViolation) {text}\n[SQL: {sql}]\n[parameters: {{'p': 1}}]", sql
        if r < 0.85:
            self.wrapped = "freetext_in_sql_block"
            return f"sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) x\n[SQL: UPDATE t SET {text}]", None
        if r < 0.93:
            self.wrapped = "pymysql_text_in_params"
            return f"(pymysql.err.OperationalError) (1045, {text})\n[SQL: SELECT 1]\n[parameters: ({text})]", None
        self.wrapped = "traceback"
        return f'Traceback (most recent call last):\n  File "a.py", line 1\n    x()\nValueError: {text}', None

    def row(self) -> dict[str, Any]:
        frags = [self.fragment() for _ in range(self.rng.randint(1, 4))]
        secrets = [secret for found, _ in frags for secret in found]
        text = frags[0][1]
        for _, part in frags[1:]:
            text += self.rng.choice(_GLUE) + part
        text, sql = self.wrap(text)
        return {"t": text, "s": secrets, "q": sql, "w": self.wrapped}


def corpus(seed: int, rows: int) -> list[dict[str, Any]]:
    generator = _Generator(seed)
    return [generator.row() for _ in range(rows)]


# --- the comparator: pure ---------------------------------------------------------------------------------------------


def shown(secret: str, text: str | None) -> str | None:
    """The part of ``secret`` that ``text`` shows: all of it, or a window of ``WINDOW`` characters, else ``None``."""
    if not text:
        return None
    if secret in text:
        return secret
    for start in range(len(secret) - WINDOW + 1):
        window = secret[start : start + WINDOW]
        if window in text and not any(window in fixed for fixed in FIXED):
            return window
    return None


def leaked(secret: str, old: str | None, new: str | None) -> str | None:
    """What ``new`` shows of ``secret`` that ``old`` hid: the regression A2 counts."""
    found = shown(secret, new)
    return found if found is not None and shown(secret, old) is None else None


def a2_hits(
    secrets: Iterable[str], old: Mapping[str, str | None], new: Mapping[str, str | None]
) -> collections.Counter[str]:
    """Per surface: the secrets the candidate shows on a surface where the baseline hid them."""
    hits: collections.Counter[str] = collections.Counter()
    for surface in A2_SURFACES:
        if surface in old and surface in new:
            hits[surface] += sum(leaked(secret, old[surface], new[surface]) is not None for secret in secrets)
    return hits


def a7_row(secrets: Iterable[str], old: str | None, new: str | None) -> tuple[bool, bool]:
    """``(differs, newly shown)`` for one row of ``mask_text`` output."""
    return old != new, any(leaked(secret, old, new) is not None for secret in secrets)


# --- the trees --------------------------------------------------------------------------------------------------------


def export(rev: str, into: Path) -> Path:
    """``git archive`` of ``rev`` into ``into``; a directory is taken as the tree itself. Returns the tree's ``src``."""
    if Path(rev).is_dir():
        return Path(rev).resolve() / "src"
    packed = subprocess.run(["git", "archive", "--format=tar", rev, "src"], cwd=ROOT, capture_output=True, check=True)
    into.mkdir()
    with tarfile.open(fileobj=io.BytesIO(packed.stdout)) as archive:
        archive.extractall(into, filter="data")
    return into / "src"


def start(label: str, src: Path, path: Path, out: Path, fields: tuple[str, ...]) -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        "--worker",
        str(src),
        str(path),
        str(out),
        ",".join(fields),
    ]
    return subprocess.Popen(command, cwd=out.parent)  # noqa: S603  # cwd: the temporary directory, never the repo


def _first(owner: Any, *names: str) -> tuple[Callable[..., Any] | None, str]:
    for name in names:
        if (found := getattr(owner, name, None)) is not None:
            return found, f"{owner.__name__.rsplit('.', 1)[-1]}.{name}"
    return None, "none"


def work(src: str, corpus_path: str, out_path: str, fields: list[str]) -> None:
    """In the tree: every field through the tree's own production function. ``sharpit`` must be the tree's."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, src)
    import inspect  # noqa: PLC0415

    import sharpit  # noqa: PLC0415
    from sharpit.engine.capture import sqltrace, traces  # noqa: PLC0415
    from sharpit.engine.masking import Exposure, Masker  # noqa: PLC0415

    assert Path(sharpit.__file__).resolve().is_relative_to(Path(src).resolve()), sharpit.__file__
    off, on = Masker(Exposure.MASKED, True), Masker(Exposure.MASKED, True, capture_parameters=True)
    error_mask, error_name = _first(sqltrace, "mask_error")
    trace_mask, trace_name = _first(traces, "_sql_message")
    trace_mask, trace_name = (trace_mask, trace_name) if trace_mask else _first(sqltrace, "trace_message", "mask_error")
    parameters = len(inspect.signature(traces._sql_attribute).parameters)  # noqa: SLF001

    def statement(text: str) -> str | None:
        args = (off, "db.statement", text) + ((False,) if parameters > 3 else ())
        return traces._sql_attribute(*args)  # noqa: SLF001

    def recorded(masker: Masker, text: str, sql: str | None) -> str | None:
        recorder = sqltrace.SqlTraceRecorder(masker, max_sql_length=10**6)
        recorder.record(
            sql or "SELECT 2", duration_ns=1, thread="t", connection_id=None, success=False, error=Exception(text)
        )
        return recorder.rows()[-1]["errorMessage"]

    def logs(masker: Masker, text: str, **kw: bool) -> str | None:
        return error_mask(masker, text, **kw) if error_mask else masker.mask_text(text)

    table: dict[str, Callable[[str, str | None], str | None]] = {
        "text_off": lambda t, q: off.mask_text(t),
        "text_on": lambda t, q: on.mask_text(t),
        "err_off": lambda t, q: logs(off, t),
        "err_on": lambda t, q: logs(on, t),
        "err_mysql": lambda t, q: logs(off, t, mysql=True) if error_mask else off.mask_text(t),
        "rec_off": lambda t, q: recorded(off, t, q),
        "rec_on": lambda t, q: recorded(on, t, q),
        "trace": lambda t, q: trace_mask(off, t) if trace_mask else off.mask_text(t),
        "statement": lambda t, q: statement(t),
    }
    meta = {"sharpit": sharpit.__file__, "version": sharpit.__version__, "logs": error_name, "trace": trace_name}
    with open(corpus_path, encoding="utf-8") as source, open(out_path, "w", encoding="utf-8") as out:
        print(json.dumps({"meta": meta}), file=out)
        for line in source:
            row = json.loads(line)
            print(json.dumps({field: table[field](row["t"], row["q"]) for field in fields}), file=out)


def read(path: Path) -> tuple[dict[str, str], Iterable[dict[str, str | None]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return json.loads(lines[0])["meta"], (json.loads(line) for line in lines[1:])


# --- the gates --------------------------------------------------------------------------------------------------------


def run(mode: str, rows: int, seed: int, candidate: str, baseline: str) -> int:
    fields = A2_SURFACES if mode == "a2" else A7_SURFACES
    with tempfile.TemporaryDirectory(prefix="masking-gate-") as tmp:
        work_dir = Path(tmp)
        data = corpus(seed, rows)
        if mode == "a7":
            data = [row for row in data if "[SQL:" not in row["t"]]
        corpus_path = work_dir / "corpus.jsonl"
        corpus_path.write_text("".join(json.dumps(row) + "\n" for row in data), encoding="utf-8")
        trees = {"baseline": baseline, "candidate": candidate}
        jobs = {}
        for label, rev in trees.items():
            jobs[label] = (
                work_dir / f"{label}.jsonl",
                start(label, export(rev, work_dir / label), corpus_path, work_dir / f"{label}.jsonl", fields),
            )
        for label, (_, process) in jobs.items():
            assert process.wait() == 0, f"the {label} worker failed"
        (old_meta, old_rows), (new_meta, new_rows) = (read(path) for path, _ in jobs.values())
        print(f"baseline  {baseline}: {old_meta}\ncandidate {candidate}: {new_meta}")
        print(f"{mode} on {len(data)} rows, seed {seed}")
        return a2_report(data, old_rows, new_rows) if mode == "a2" else a7_report(data, old_rows, new_rows)


def a2_report(
    data: list[dict[str, Any]], old_rows: Iterable[dict[str, Any]], new_rows: Iterable[dict[str, Any]]
) -> int:
    total: collections.Counter[str] = collections.Counter()
    shortest: dict[str, tuple[str, str, str | None, str | None]] = {}
    for row, old, new in zip(data, old_rows, new_rows, strict=True):
        hits = a2_hits(row["s"], old, new)
        total += hits
        for surface in +hits:
            if surface not in shortest or len(row["t"]) < len(shortest[surface][1]):
                fragment = next(f for s in row["s"] if (f := leaked(s, old[surface], new[surface])))
                shortest[surface] = (fragment, row["t"], old[surface], new[surface])
    for surface, (fragment, text, was, now) in shortest.items():
        print(f"  shortest on {surface}: shows {fragment!r}\n    in  {text[:200]!r}")
        print(f"    was {was!r:.200}\n    now {now!r:.200}")
    for surface in A2_SURFACES:
        print(f"  {surface:10} {total[surface]:6} secrets shown that the baseline hid")
    print(f"A2 {'PASS' if not total else 'FAIL'}: {sum(total.values())} secrets back")
    return int(bool(total))


def a7_report(
    data: list[dict[str, Any]], old_rows: Iterable[dict[str, Any]], new_rows: Iterable[dict[str, Any]]
) -> int:
    differ = newly = 0
    for row, old, new in zip(data, old_rows, new_rows, strict=True):
        for field in A7_SURFACES:
            changed, worse = a7_row(row["s"], old[field], new[field])
            differ += changed
            newly += worse
    print(f"A7 {'PASS' if not newly else 'FAIL'}: {differ} outputs differ, {newly} secrets newly shown")
    return int(bool(newly))


def main(argv: list[str]) -> int:
    if argv[:1] == ["--worker"]:
        work(argv[1], argv[2], argv[3], argv[4].split(","))
        return 0
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("a2", "a7"))
    parser.add_argument("--rows", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--candidate", default="HEAD", help="a commit, tag or tree-ish, or a checkout's directory")
    parser.add_argument("--baseline", help="default: v0.4.0 for a2, fa2d51e for a7")
    args = parser.parse_args(argv)
    return run(args.mode, args.rows, args.seed, args.candidate, args.baseline or BASELINES[args.mode])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
