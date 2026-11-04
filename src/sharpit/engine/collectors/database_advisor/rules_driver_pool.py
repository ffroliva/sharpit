"""Driver and pool rules DB-DRIVER-007/008 and DB-POOL-001..004 (sharpit's SQLAlchemy analogues of BootUI's JDBC
driver and HikariCP/Agroal checks, 2.2.0).

Evidence is the engine object (``echo``, the pool class and its effective numbers), the presence of an allow-listed URL
query key, and the server limits read in the same bounded catalog read. A value from the URL is never read, and neither
is ``url.password``; a finding is keyed by datasource and setting, never by value. SQLAlchemy pools have no idle
timeout and no keepalive: ``pool_recycle`` is the maximum lifetime and ``pool_pre_ping`` the liveness check that
covers a connection the server closed.
"""

from __future__ import annotations

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Pool, Rule, Source

DRIVER = "Driver"
POOL = "Connection pool"
POOL_SHARE_PERCENT = 50


_LIBPQ_STYLE = frozenset({"psycopg", "psycopg2", "pg8000"})  # no connect timeout unless one is configured
_SERVERS = ("postgresql", "mysql", "mariadb")
NO_LIMIT = -1.0  # the server enforces no idle-session limit


def _echo(source: Source) -> Outcome:
    if not source.echo:
        return []
    text = f"Datasource `{source.name}`: the engine logs every statement (echo is on). Evidence: configured."
    return [(source.name, text, f"ds={source.name}|setting=echo")]


def _connect_timeout(source: Source) -> Outcome:
    if source.dialect != "postgresql" or source.driver not in _LIBPQ_STYLE:
        return f"Datasource {source.name} uses {source.dialect}+{source.driver}, which this check does not judge."
    if "connect_timeout" in source.url_keys:
        return []
    text = (
        f"Datasource `{source.name}`: connect_timeout is not configured in the URL, so opening a connection can wait "
        "without a limit. Evidence: configured."
    )
    return [(source.name, text, f"ds={source.name}|setting=connect_timeout")]


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _applies(source: Source) -> str | None:
    """Why the pool rules cannot judge ``source``, else None."""
    if source.dialect not in _SERVERS:
        return f"Datasource {source.name} ({source.dialect}) has no server connection limits to compare a pool with."
    if source.pool is None:
        return f"The connection pool of datasource {source.name} could not be read."
    return None


def _usable(source: Source) -> int | None:
    """The connections an ordinary role may hold, or None when a limit is missing or does not parse."""
    server = source.server
    total = _int(server.get("max_connections"))
    if source.dialect != "postgresql" or total is None:
        return total
    reserved = _int(server.get("superuser_reserved_connections"))
    extra = _int(server.get("reserved_connections", "0"))  # PostgreSQL 16+; absent before
    return None if reserved is None or extra is None else total - reserved - extra


def _seconds(value: int | None, per_second: int) -> float | None:
    """``value`` in seconds; ``NO_LIMIT`` at zero or below, None when unread."""
    if value is None:
        return None
    return NO_LIMIT if value <= 0 else value / per_second


def _idle_limit_seconds(source: Source) -> float | None:
    """The server's idle-session limit in seconds, ``NO_LIMIT``, or None when unknown."""
    server = source.server
    if source.dialect == "postgresql":
        if not server:  # the settings read failed: the version, and so the feature, is unknown
            return None
        if "idle_session_timeout" not in server:  # before PostgreSQL 14 there is no such limit
            return NO_LIMIT
        return _seconds(_int(server["idle_session_timeout"]), 1000)
    return _seconds(_int(server.get("wait_timeout")), 1)


def _idle_fires(source: Source, pool: Pool) -> bool | str:
    """Whether DB-POOL-001 fires (shared with DB-POOL-003, so ownership cannot drift), or why that is unsettled."""
    if pool.pre_ping:  # a closed connection is replaced at checkout
        return False
    limit = _idle_limit_seconds(source)
    if limit is None:
        return f"the idle-session limit of datasource {source.name}'s server could not be read"
    if limit == NO_LIMIT:
        return False
    if pool.recycle is None or pool.pre_ping is None:
        return f"the pool settings of datasource {source.name} could not be read"
    return pool.recycle < 0 or pool.recycle >= limit


def _idle_limit(source: Source) -> Outcome:
    if (reason := _applies(source)) is not None or source.pool is None:
        return reason or ""
    fires = _idle_fires(source, source.pool)
    if isinstance(fires, str):
        return f"Not evaluated: {fires}."
    if not fires:
        return []
    text = (
        f"Datasource `{source.name}`: pool_recycle {source.pool.recycle} and pool_pre_ping off, while the server "
        f"closes a session idle for {_idle_limit_seconds(source):g} s: the pool may hand out a connection the server "
        "has already closed. Evidence: effective."
    )
    return [(source.name, text, f"ds={source.name}|pool=idle-limit")]


def _unlimited_lifetime(source: Source) -> Outcome:
    if (reason := _applies(source)) is not None or source.pool is None:
        return reason or ""
    if source.pool.recycle is None:
        return f"The pool_recycle of datasource {source.name} could not be read."
    if source.pool.recycle >= 0:
        return []
    fires = _idle_fires(source, source.pool)
    if isinstance(fires, str):  # whether DB-POOL-001 owns this datasource is unsettled: never guess
        return f"Undecided: {fires}, so whether DB-POOL-001 reports this datasource is unsettled."
    if fires:
        return []
    text = f"Datasource `{source.name}`: pool_recycle is -1, so a connection is never retired for age."
    text += " Evidence: effective."
    return [(source.name, text, f"ds={source.name}|pool=max-lifetime")]


def _fit(source: Source) -> tuple[int, int | None] | str:
    """``(usable, maximum size or None when unbounded)``, or why the capacity rules cannot judge ``source``."""
    if (reason := _applies(source)) is not None or source.pool is None:
        return reason or ""
    usable = _usable(source)
    if usable is None:
        return f"The connection limit of datasource {source.name}'s server could not be read."
    if not source.pool.unbounded and source.pool.max_size is None:
        return f"The {source.pool.kind} of datasource {source.name} has no fixed maximum size."
    return usable, None if source.pool.unbounded else source.pool.max_size


def _exceeds(usable: int, size: int | None) -> bool:
    return size is None or size > usable


def _exceeds_server(source: Source) -> Outcome:
    fit = _fit(source)
    if isinstance(fit, str):
        return fit
    usable, size = fit
    if not _exceeds(usable, size):
        return []
    shown = "unbounded (max_overflow -1)" if size is None else str(size)
    text = (
        f"Datasource `{source.name}`: the pool's maximum size {shown} exceeds the {usable} usable connections: the "
        "pool cannot fill, unless a proxy multiplexes. Evidence: effective."
    )
    return [(source.name, text, f"ds={source.name}|pool=maximum-size")]


def _server_share(source: Source) -> Outcome:
    fit = _fit(source)
    if isinstance(fit, str):
        return fit
    usable, size = fit
    if size is None or _exceeds(usable, size) or size * 100 <= usable * POOL_SHARE_PERCENT:
        return []
    text = (
        f"Datasource `{source.name}`: the pool's maximum size {size} is over {POOL_SHARE_PERCENT}% of the {usable} "
        "usable connections; a second instance would not fit. Heuristic. Evidence: effective."
    )
    return [(source.name, text, f"ds={source.name}|pool=maximum-size")]


RULES = (
    Rule(
        RuleDefinition(
            "DB-DRIVER-007",
            "Engine statement logging is enabled",
            DRIVER,
            "LOW",
            "Detects an engine created with echo (or echo_pool) on, which logs every statement, and its parameters "
            "when echo is 'debug', through the sqlalchemy.engine logger and adds overhead while on.",
            "Turn echo off once the investigation it was enabled for is over, or enable it only in an environment "
            "where its overhead and log volume do not matter.",
            "https://docs.sqlalchemy.org/en/20/core/engines.html#sqlalchemy.create_engine.params.echo",
        ),
        _echo,
    ),
    Rule(
        RuleDefinition(
            "DB-DRIVER-008",
            "PostgreSQL driver has no connect timeout",
            DRIVER,
            "LOW",
            "Detects a PostgreSQL datasource on psycopg, psycopg2 or pg8000 whose URL does not configure "
            "connect_timeout. These drivers wait without a limit by default, so a request can hang on an unreachable "
            "server. Only the URL's query keys are read, for presence: a timeout passed through connect_args is not "
            "visible.",
            "Set connect_timeout in the URL (or in connect_args, then dismiss this finding) to a few seconds, longer "
            "than a healthy connection takes to open, and measure.",
            "https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-CONNECT-TIMEOUT",
        ),
        _connect_timeout,
    ),
    Rule(
        RuleDefinition(
            "DB-POOL-001",
            "Connection pool can keep a connection idle longer than the server allows",
            POOL,
            "MEDIUM",
            "Detects a pool on a PostgreSQL, MySQL or MariaDB datasource that can hold an idle connection longer than "
            "the server lets a session stay idle (MySQL/MariaDB wait_timeout, PostgreSQL idle_session_timeout when "
            "above 0): pool_recycle is -1 or not below the server limit, and pool_pre_ping is off. The pool may then "
            "hand out a connection the server has already closed. The server value is the one the scan connection's "
            "own session sees.",
            "Set pool_recycle several seconds shorter than the server's idle-session limit, or turn on pool_pre_ping "
            "so a closed connection is replaced at checkout. Or raise the server limit (MySQL wait_timeout) or disable "
            "it for pooled roles (PostgreSQL idle_session_timeout).",
            "https://docs.sqlalchemy.org/en/20/core/pooling.html#dealing-with-disconnects",
        ),
        _idle_limit,
    ),
    Rule(
        RuleDefinition(
            "DB-POOL-002",
            "Connection pool is larger than the server's connection limit",
            POOL,
            "MEDIUM",
            "Detects a pool on a PostgreSQL, MySQL or MariaDB datasource whose maximum size (pool_size plus "
            "max_overflow, or no maximum at all) is larger than the connections the server lets an ordinary role "
            "hold: max_connections, minus superuser_reserved_connections and, from PostgreSQL 16, "
            "reserved_connections. Such a pool cannot fill, and other clients of the same server count against the "
            "same limit. A proxy that multiplexes connections (PgBouncer, RDS Proxy, ProxySQL) is not visible from "
            "here.",
            "Lower pool_size plus max_overflow below the server's usable connections, leaving room for other "
            "clients, or raise max_connections if the server can afford it. If a connection proxy sits between the "
            "application and the database, verify its own limits instead and dismiss this finding.",
            "https://docs.sqlalchemy.org/en/20/core/pooling.html#sqlalchemy.pool.QueuePool",
        ),
        _exceeds_server,
    ),
    Rule(
        RuleDefinition(
            "DB-POOL-003",
            "Connection pool has no maximum connection lifetime",
            POOL,
            "LOW",
            "Detects a pool on a PostgreSQL, MySQL or MariaDB datasource whose pool_recycle is -1 (the default), so a "
            "connection is never retired for age. It stays quiet when DB-POOL-001 reports the datasource, because "
            "that finding already includes this setting.",
            "Set pool_recycle well below the shortest connection limit on the path to the database (a firewall or "
            "load balancer idle timeout, a server-side limit), or keep it unlimited deliberately and rely on "
            "pool_pre_ping, then dismiss this finding.",
            "https://docs.sqlalchemy.org/en/20/core/pooling.html#setting-pool-recycle",
        ),
        _unlimited_lifetime,
    ),
    Rule(
        RuleDefinition(
            "DB-POOL-004",
            "Connection pool leaves no headroom for a second instance",
            POOL,
            "LOW",
            f"Detects a pool on a PostgreSQL, MySQL or MariaDB datasource whose maximum size is more than "
            f"{POOL_SHARE_PERCENT} percent of the connections the server lets an ordinary role hold (see DB-POOL-002 "
            "for how they are counted), yet still fits. It is a heuristic that assumes a second instance of the "
            "application will open a pool of the same size on the same server; it knows nothing about other clients. "
            "It stays quiet when DB-POOL-002 reports the datasource.",
            "Size the pool for the application's real concurrency rather than the server's capacity, so every "
            "instance and the other clients fit together. Dismiss this finding when the application never runs more "
            "than one instance on this server, or when a connection proxy multiplexes the connections.",
            "https://docs.sqlalchemy.org/en/20/core/pooling.html#sqlalchemy.pool.QueuePool",
        ),
        _server_share,
    ),
)
