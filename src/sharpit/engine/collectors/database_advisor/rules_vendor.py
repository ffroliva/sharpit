"""Vendor rules (port of BootUI 2.2.0): DB-PG-001..005 and DB-SERVER-001/002 on PostgreSQL, DB-MYSQL-001..003 and
DB-SCHEMA-010 on MySQL/MariaDB. ``DB-ORACLE-*`` is dropped (no verified read-only path, spec §5.0).

``read_vendor(conn, bounds)`` runs fixed catalog statements (no parameters, no ``%``) inside the advisor's read-only
read: on PostgreSQL each in a savepoint, so a denied view does not abort the transaction. Each fact is its rows (at
most ``bounds.vendor_rows``) or the error's first line. A rule on another dialect, a fact not read or a failed read is
``SKIPPED`` with the reason, never a pass.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sharpit.engine.advisors.rules import RuleDefinition, Severity
from sharpit.engine.collectors.database_advisor.catalog import Hit, Outcome, Rule, Source, unreadable
from sharpit.engine.masking import Masker
from sharpit.engine.sqla.inspect import CatalogBounds, error_text
from sharpit.engine.sqltext import Dialect, dialect_of_name

PG = ("postgresql",)
MYSQL = ("mysql", "mariadb")
THRESHOLD = 0.8
NOT_READ = "The vendor catalog was not read for this scan."
NONTRANSACTIONAL = frozenset({"MYISAM", "MRG_MYISAM", "MERGE", "MEMORY", "HEAP", "ARCHIVE", "CSV", "ARIA"})
_INT_MAX = {"tinyint": 127, "smallint": 32767, "mediumint": 8388607, "int": 2147483647, "integer": 2147483647,
            "bigint": 9223372036854775807}  # fmt: skip

_PG_SQL = {
    "invalidIndexes": "SELECT t.relname AS tbl, c.relname AS idx FROM pg_index i "
    "JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_class t ON t.oid = i.indrelid "
    "JOIN pg_namespace n ON n.oid = t.relnamespace WHERE n.nspname = current_schema() AND t.relkind <> 'p' "
    "AND NOT (i.indisvalid AND i.indisready AND i.indislive) "
    "AND NOT EXISTS (SELECT 1 FROM pg_stat_progress_create_index p WHERE p.index_relid = i.indexrelid) ORDER BY 1, 2",
    "sequences": "SELECT sequencename AS seq, last_value, min_value, max_value, increment_by FROM pg_sequences "
    "WHERE schemaname = current_schema() ORDER BY 1",
    "notValid": "SELECT t.relname AS tbl, con.conname AS name FROM pg_constraint con "
    "JOIN pg_class t ON t.oid = con.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace "
    "WHERE n.nspname = current_schema() AND NOT con.convalidated ORDER BY 1, 2",
    "replicaIdentity": "SELECT DISTINCT c.relname AS tbl, c.relreplident::text AS identity, "
    "EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid AND i.indisprimary) AS has_pk, "
    "EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid AND i.indisreplident AND i.indisvalid) AS has_index "
    "FROM pg_publication p JOIN pg_publication_tables pt ON pt.pubname = p.pubname "
    "JOIN pg_namespace n ON n.nspname = pt.schemaname "
    "JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = pt.tablename "
    "WHERE (p.pubupdate OR p.pubdelete) AND pt.schemaname = current_schema() ORDER BY 1",
    "unlogged": "SELECT c.relname AS tbl FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = current_schema() AND c.relkind = 'r' AND c.relpersistence = 'u' AND NOT EXISTS "
    "(SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e') "
    "ORDER BY 1",
    # reset_val: the role/database/server value, not the statement timeout the advisor's own read sets
    "settings": "SELECT name, reset_val AS setting FROM pg_settings "
    "WHERE name IN ('idle_in_transaction_session_timeout', 'statement_timeout')",
}
_MYSQL_SQL = {
    "engines": "SELECT TABLE_NAME AS tbl, ENGINE AS engine FROM information_schema.TABLES "
    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' ORDER BY 1",
    "utf8mb3": "SELECT TABLE_NAME AS tbl, NULL AS col FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
    "AND TABLE_TYPE = 'BASE TABLE' AND SUBSTRING_INDEX(TABLE_COLLATION, '_', 1) IN ('utf8', 'utf8mb3') "
    "UNION ALL SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
    "AND CHARACTER_SET_NAME IN ('utf8', 'utf8mb3') ORDER BY 1, 2",
    "autoIncrement": "SELECT t.TABLE_NAME AS tbl, c.COLUMN_NAME AS col, c.COLUMN_TYPE AS column_type, "
    "t.AUTO_INCREMENT AS next_value FROM information_schema.TABLES t JOIN information_schema.COLUMNS c "
    "ON c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME WHERE t.TABLE_SCHEMA = DATABASE() "
    "AND t.AUTO_INCREMENT IS NOT NULL AND LOCATE('auto_increment', c.EXTRA) > 0 ORDER BY 1",
}
_INVISIBLE_SQL = "SELECT DISTINCT TABLE_NAME AS tbl, INDEX_NAME AS idx FROM information_schema.STATISTICS " \
    "WHERE TABLE_SCHEMA = DATABASE() AND {} ORDER BY 1, 2"  # fmt: skip


def _statements(dialect: Any) -> dict[str, str]:
    name = str(getattr(dialect, "name", ""))
    if name in PG:
        return _PG_SQL
    if name not in MYSQL:
        return {}
    mariadb = name == "mariadb" or getattr(dialect, "is_mariadb", False) is True
    return {**_MYSQL_SQL, "invisible": _INVISIBLE_SQL.format("IGNORED = 'YES'" if mariadb else "IS_VISIBLE = 'NO'")}


def _fetch(conn: Any, sql: str, limit: int) -> tuple[list[str], list[Any]]:
    result = conn.exec_driver_sql(sql)
    return list(result.keys()), result.fetchmany(limit + 1)


def read_vendor(conn: Any, bounds: CatalogBounds, masker: Masker) -> dict[str, Any]:
    """The vendor facts behind ``conn`` (run it inside the read-only read); ``{}`` on any other dialect."""
    facts: dict[str, Any] = {}
    savepoint = conn.dialect.name in PG  # a failed statement must not abort the read's transaction
    dialect = dialect_of_name(conn.dialect.name) or Dialect.UNSUPPORTED
    for name, sql in _statements(conn.dialect).items():
        try:
            if savepoint:
                with conn.begin_nested():
                    keys, rows = _fetch(conn, sql, bounds.vendor_rows)
            else:
                keys, rows = _fetch(conn, sql, bounds.vendor_rows)
        except Exception as exc:  # noqa: BLE001 - one denied view skips its rules; never the scan
            facts[name] = {"error": error_text(exc, masker, dialect)}
            continue
        kept = [dict(zip(keys, row, strict=True)) for row in rows[: bounds.vendor_rows]]
        facts[name] = {"rows": kept, "truncated": len(rows) > bounds.vendor_rows}
    return facts


# --- the checks --------------------------------------------------------------------------------------------------


def _rows(source: Source, dialects: tuple[str, ...], fact: str) -> list[dict[str, Any]] | str:
    if source.dialect not in dialects:
        return f"This check reads the {' or '.join(dialects)} catalog; datasource {source.name} is {source.dialect}."
    if (reason := unreadable(source)) is not None:
        return reason
    found = source.catalog.get("vendor", {}).get(fact)
    if found is None:
        return NOT_READ
    if "error" in found:
        return f"The {fact} catalog read failed: {found['error']}"
    return found["rows"]


def _hit(source: Source, where: str, text: str, *parts: str) -> Hit:
    return f"{source.name}/{where}", f"Datasource `{source.name}`: {text}", "|".join((f"ds={source.name}", *parts))


def _listed(dialects: tuple[str, ...], fact: str, text: str) -> Callable[[Source], Outcome]:
    """A rule whose every row is one finding: ``text`` formats a row (``tbl``, ``idx``, ``name``)."""

    def check(source: Source) -> Outcome:
        rows = _rows(source, dialects, fact)
        if isinstance(rows, str):
            return rows
        hits: list[Hit] = []
        for row in rows:
            k = "idx" if "idx" in row else "name"
            where = row["tbl"] + (f".{row[k]}" if k in row else "")
            hits.append(_hit(source, where, text.format(**row), f"table={row['tbl']}", f"object={where}"))
        return hits

    return check


def _consumed(row: dict[str, Any]) -> float | None:
    """The share of a sequence's range used, direction-aware; None when unread (``last_value`` null) or degenerate."""
    if row["last_value"] is None:
        return None
    low, high, last = int(row["min_value"]), int(row["max_value"]), int(row["last_value"])
    if high <= low:
        return None
    return (last - low) / (high - low) if int(row["increment_by"]) > 0 else (high - last) / (high - low)


def _sequences(source: Source) -> Outcome:
    rows = _rows(source, PG, "sequences")
    if isinstance(rows, str):
        return rows
    return [
        _hit(
            source, row["seq"], f"sequence `{row['seq']}` has used {share:.0%} of its range.", f"sequence={row['seq']}"
        )
        for row in rows
        if (share := _consumed(row)) is not None and share >= THRESHOLD
    ]


def _replica_identity(source: Source) -> Outcome:
    rows = _rows(source, PG, "replicaIdentity")
    if isinstance(rows, str):
        return rows
    unusable = [
        row
        for row in rows
        if row["identity"] == "n"
        or (row["identity"] == "d" and not row["has_pk"])
        or (row["identity"] == "i" and not row["has_index"])
    ]
    text = "table `{}` is published for UPDATE/DELETE without a usable replica identity."
    return [_hit(source, row["tbl"], text.format(row["tbl"]), f"table={row['tbl']}") for row in unusable]


def _capacity(column_type: str) -> int | None:
    base = re.match(r"\s*([a-z]+)", column_type.lower())
    top = _INT_MAX.get(base.group(1)) if base else None
    if top is None:
        return None
    return top * 2 + 1 if "unsigned" in column_type.lower() else top


def _auto_increment(source: Source) -> Outcome:
    rows = _rows(source, MYSQL, "autoIncrement")
    if isinstance(rows, str):
        return rows
    hits: list[Hit] = []
    for row in rows:
        top = _capacity(str(row["column_type"]))
        if top is not None and row["next_value"] is not None and int(row["next_value"]) >= THRESHOLD * top:
            where = f"{row['tbl']}.{row['col']}"
            text = f"AUTO_INCREMENT of `{where}` ({row['column_type']}) is at {int(row['next_value']) / top:.0%}."
            hits.append(_hit(source, where, text, f"table={row['tbl']}", f"column={row['col']}"))
    return hits


def _engines(source: Source) -> Outcome:
    rows = _rows(source, MYSQL, "engines")
    if isinstance(rows, str):
        return rows
    text = "table `{tbl}` uses the non-transactional {engine} storage engine."
    return [
        _hit(source, row["tbl"], text.format(**row), f"table={row['tbl']}")
        for row in rows
        if str(row["engine"] or "").upper() in NONTRANSACTIONAL
    ]


def _utf8mb3(source: Source) -> Outcome:
    rows = _rows(source, MYSQL, "utf8mb3")
    if isinstance(rows, str):
        return rows
    hits: list[Hit] = []
    for row in rows:
        where = row["tbl"] if row["col"] is None else f"{row['tbl']}.{row['col']}"
        noun = "table" if row["col"] is None else "column"
        hits.append(_hit(source, where, f"{noun} `{where}` uses the legacy utf8mb3 character set.", f"{noun}={where}"))
    return hits


def _setting(name: str, text: str) -> Callable[[Source], Outcome]:
    def check(source: Source) -> Outcome:
        rows = _rows(source, PG, "settings")
        if isinstance(rows, str):
            return rows
        value = next((str(row["setting"]) for row in rows if row["name"] == name), None)
        if value is None:
            return f"The server did not report {name}."
        return [_hit(source, name, text, f"setting={name}")] if value == "0" else []

    return check


def _rule(rule_id: str, title: str, category: str, severity: Severity, description: str, recommendation: str,
          url: str, check: Callable[[Source], Outcome]) -> Rule:  # fmt: skip
    return Rule(RuleDefinition(rule_id, title, category, severity, description, recommendation, url), check)


_REVIEW = "A review prompt, not a verdict: confirm the state on the server before changing anything."

RULES = (
    _rule("DB-SCHEMA-010", "Invisible or ignored indexes", "Schema", "LOW",
          "Reports a MySQL 8.0+ invisible (STATISTICS.IS_VISIBLE = 'NO') or MariaDB 10.6+ ignored (IGNORED = 'YES') "
          "index: the optimizer does not use it, yet every write still maintains it.",
          "Decide whether the soft drop or trial is finished, then make the index visible again or drop it. " + _REVIEW,
          "https://dev.mysql.com/doc/refman/8.4/en/invisible-indexes.html",
          _listed(MYSQL, "invisible", "index `{idx}` on `{tbl}` is invisible to the optimizer.")),
    _rule("DB-PG-001", "Invalid PostgreSQL indexes", "PostgreSQL", "HIGH",
          "Reports an index that is not valid, ready or live (a failed concurrent build), excluding builds in "
          "progress and partitioned parents. An invalid UNIQUE index may still reject duplicates.",
          "Confirm the build state and dependencies, then rebuild the index. " + _REVIEW,
          "https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY",
          _listed(PG, "invalidIndexes", "index `{idx}` on `{tbl}` is invalid.")),
    _rule("DB-PG-002", "PostgreSQL sequence nearing exhaustion", "PostgreSQL", "HIGH",
          "Reviews a sequence's last value against its direction-aware bounds; 80% used is reported. A sequence "
          "never read (null last_value) is not assessed. The owning column's narrower type is not compared.",
          "Review the sequence and column bounds together; the threshold is a snapshot, not time left. " + _REVIEW,
          "https://www.postgresql.org/docs/current/view-pg-sequences.html", _sequences),
    _rule("DB-PG-003", "PostgreSQL NOT VALID constraint never validated", "PostgreSQL", "MEDIUM",
          "Reports a constraint currently not validated: new rows are checked, existing rows are not.",
          "Review the intended migration stage, then VALIDATE CONSTRAINT. " + _REVIEW,
          "https://www.postgresql.org/docs/current/sql-altertable.html",
          _listed(PG, "notValid", "constraint `{name}` on `{tbl}` is NOT VALID.")),
    _rule("DB-PG-004", "PostgreSQL table lacking usable replica identity", "PostgreSQL", "MEDIUM",
          "Reviews a table in a publication that publishes UPDATE or DELETE whose replica identity is NOTHING, "
          "DEFAULT without a primary key, or an index that is missing or invalid.",
          "Choose a primary key, a supported identity index or REPLICA IDENTITY FULL. " + _REVIEW,
          "https://www.postgresql.org/docs/current/logical-replication-publication.html", _replica_identity),
    _rule("DB-PG-005", "PostgreSQL unlogged tables", "PostgreSQL", "LOW",
          "Reports an ordinary table with relpersistence = 'u' (not extension-owned): it is truncated after a crash "
          "and not replicated to physical standbys.",
          "If the data must be durable, ALTER TABLE ... SET LOGGED. " + _REVIEW,
          "https://www.postgresql.org/docs/current/sql-createtable.html#SQL-CREATETABLE-UNLOGGED",
          _listed(PG, "unlogged", "table `{tbl}` is UNLOGGED.")),
    _rule("DB-MYSQL-001", "Tables on a non-transactional storage engine", "MySQL", "MEDIUM",
          "Reviews a table on a known non-transactional engine (MyISAM, MEMORY, ARCHIVE, CSV, MERGE, Aria).",
          "Review the application's transaction requirements and the migration cost. " + _REVIEW,
          "https://dev.mysql.com/doc/refman/8.4/en/storage-engines.html", _engines),
    _rule("DB-MYSQL-002", "Tables/columns using the legacy utf8mb3 character set", "MySQL", "MEDIUM",
          "Reviews a table default or a column encoded utf8/utf8mb3, which cannot hold the full Unicode range.",
          "Review index lengths and collation semantics before converting to utf8mb4. " + _REVIEW,
          "https://dev.mysql.com/doc/refman/8.4/en/charset-unicode-utf8mb3.html", _utf8mb3),
    _rule("DB-MYSQL-003", "MySQL/MariaDB AUTO_INCREMENT nearing exhaustion", "MySQL", "HIGH",
          "Reviews a reported AUTO_INCREMENT counter at or beyond 80% of its signed/unsigned integer column's "
          "capacity. The counter can be cached or stale; it is not a row count.",
          "Review the column bounds and the referencing columns; never reset a counter blindly. " + _REVIEW,
          "https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html", _auto_increment),
    _rule("DB-SERVER-001", "PostgreSQL does not end sessions that are idle in a transaction", "Server", "LOW",
          "Fires when idle_in_transaction_session_timeout is 0 for the role (pg_settings.reset_val): a session left "
          "idle in a transaction keeps its locks and holds back vacuum.",
          "Set a limit on the role the application uses, unless it only runs short, trusted transactions.",
          "https://www.postgresql.org/docs/current/runtime-config-client.html",
          _setting("idle_in_transaction_session_timeout", "idle_in_transaction_session_timeout is 0.")),
    _rule("DB-SERVER-002", "PostgreSQL has no statement timeout", "Server", "LOW",
          "Fires when statement_timeout is 0 for the role (pg_settings.reset_val, not the advisor's own read): the "
          "server never aborts a runaway statement.",
          "Set a limit on the role the application's requests use; a migration role may need none.",
          "https://www.postgresql.org/docs/current/runtime-config-client.html",
          _setting("statement_timeout", "statement_timeout is 0.")),
)  # fmt: skip
