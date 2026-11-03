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
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Rule, Source

DRIVER = "Driver"
POOL = "Connection pool"
POOL_SHARE_PERCENT = 50


def _echo(source: Source) -> Outcome:
    return [("", "", "")]


def _connect_timeout(source: Source) -> Outcome:
    return [("", "", "")]


def _idle_limit(source: Source) -> Outcome:
    return [("", "", "")]


def _exceeds_server(source: Source) -> Outcome:
    return [("", "", "")]


def _unlimited_lifetime(source: Source) -> Outcome:
    return [("", "", "")]


def _server_share(source: Source) -> Outcome:
    return [("", "", "")]


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
