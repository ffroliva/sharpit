"""ORM evidence for the test session: relationship loads (N+1), eager batches and unbounded reads."""

# pyright: reportPrivateUsage=false
# the package was one module until 0.5.0; its submodules share private state

from __future__ import annotations

import ast
import functools
import inspect
import linecache
import operator
import sys
from types import CodeType
from typing import Any, cast

from sharpit.engine.capture.correlation import REQUEST, TEST, paging_of
from sharpit.engine.capture.frames import is_application_frame
from sharpit.engine.masking import Masker
from sharpit.engine.sources import dispatch
from sharpit.engine.sqla import _lock
from sharpit.engine.sqltext import Dialect, dialect_of_name
from sharpit.engine.testsession.facts import PhaseFacts, UnboundedReadFact
from sharpit.engine.testsession.gates import LAZY_LOAD_OUTSIDE_APP

RELATIONSHIP_KEY = "sharpit_relationship"
_EAGER_RELATIONSHIP_KEY = "sharpit_eager_relationship"

_relationship_loads: dict[tuple[str, int, str], dict[str, int]] = {}
_relationship_groups: dict[tuple[str, int, str], dict[str, tuple[str, bool]]] = {}
_relationship_sites: dict[tuple[str, int, str], dict[str, str | None]] = {}
# raw statement -> (application site, batched-query hint) per test, None until the statement repeats: a statement
# that runs once never pays the stack walk, a later repeat costs one dict lookup
_statement_sites: dict[tuple[str, int, str], dict[tuple[str, Dialect], tuple[str | None, str] | None]] = {}
# shortcut: distinct statements per test (literal-inlined SQL is distinct per value); a repeat first seen after the
# cap gets the plain message. Upgrade if real suites hit it: key by the masked fingerprint instead.
MAX_STATEMENT_SITES = 256
GENERIC_BATCH = "one SELECT with WHERE ... IN (...) over all the ids"
_eager_relationship_batches: dict[tuple[str, int, str], dict[str, int]] = {}
_unbounded_read_facts: dict[tuple[str, int, str], dict[str, UnboundedReadFact]] = {}
_unbounded_read_missing_capture: set[tuple[str, int]] = set()
_unbounded_read_capture_missing = False
_unbounded_read_request_seen = False
_unbounded_read_factor = 2
# lazy loads already recorded per test: (compiled, parent class, statement) decides the whole outcome, so a repeat
# (the N in N+1) skips the path read and the fingerprint; the lazy-load overhead budget depends on it
_lazy_seen: dict[tuple[str, int, str], set[tuple[Any, Any, str]]] = {}


@functools.lru_cache(maxsize=4096)
def _is_application_code(code: CodeType) -> bool:
    return is_application_frame(code.co_filename)


def _first_application_location() -> str | None:
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame is not None else None
        while frame is not None:
            if _is_application_code(frame.f_code):
                return f"{frame.f_code.co_filename}:{frame.f_lineno}"
            frame = frame.f_back
        return None
    finally:
        del frame


def _binds(statement: ast.stmt, key: str) -> bool:
    target = statement.target if isinstance(statement, ast.AnnAssign) else None
    targets = statement.targets if isinstance(statement, ast.Assign) else [target]
    return any(isinstance(t, ast.Name) and t.id == key for t in targets)


@functools.lru_cache(maxsize=256)
def _declaration_line(cls: type, key: str) -> str | None:
    """``path:line`` of ``key = relationship(...)`` in ``cls``'s body, when the class is application code."""
    filename = getattr(sys.modules.get(cls.__module__), "__file__", None)
    if not isinstance(filename, str) or not is_application_frame(filename):
        return None
    try:
        tree = ast.parse("".join(linecache.getlines(filename)))
    except (SyntaxError, ValueError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls.__name__:
            for statement in node.body:
                if _binds(statement, key):
                    return f"{filename}:{statement.lineno}"
    return None


def _declared_outside(prop: Any, identity: str) -> str | None:
    """No application frame on the stack (the load ran in response serialization): name the relationship's own line."""
    cls = getattr(getattr(prop, "parent", None), "class_", None)
    line = _declaration_line(cls, prop.key) if isinstance(cls, type) else None
    return None if line is None else f"{LAZY_LOAD_OUTSIDE_APP} ({identity} declared at {line})"


@functools.lru_cache(maxsize=1)
def _relationship_masker() -> Masker:
    from sharpit.engine.testsession.sink import report_masker

    return report_masker()


@functools.lru_cache(maxsize=1024)
def _masked_fingerprint(statement: str, dialect: Dialect) -> str | None:
    from sharpit.engine.capture.statement import masked_shape

    return masked_shape(_relationship_masker(), statement, dialect).fingerprint


def _dialect_of(owner: object) -> Dialect:
    """What a connection, engine or execution context talks to."""
    found = dialect_of_name(getattr(getattr(owner, "dialect", None), "name", None))
    return Dialect.UNSUPPORTED if found is None else found


def _relationship_path(context: Any) -> tuple[Any, str, str, int] | None:
    compiled = getattr(context, "compiled", None)
    compile_state = getattr(compiled, "compile_state", None)
    current_path = getattr(compile_state, "current_path", None)
    path = getattr(current_path, "path", ())
    if not path:
        return None
    prop = path[-1]
    key = getattr(prop, "key", None)
    direction = getattr(getattr(prop, "direction", None), "name", "")
    if not isinstance(key, str) or not direction:
        return None
    return prop, key, direction, len(path)


def _relationship_observation(context: Any, tag: tuple[str, int, str]) -> Any:
    options = getattr(context, "execution_options", {})
    relation_value = options.get(RELATIONSHIP_KEY) if options is not None else None
    if relation_value is not None:
        return relation_value
    load_options = options.get("_sa_orm_load_options") if options is not None else None
    parent = getattr(load_options, "_lazy_loaded_from", None)
    path_info = _relationship_path(context)
    if path_info is None:
        return None
    prop, key, direction, path_length = path_info
    if parent is None:
        if path_length < 2:
            return None
        parent_mapper = getattr(prop, "parent", None)
        model_name = getattr(getattr(parent_mapper, "class_", None), "__name__", None)
        return _EAGER_RELATIONSHIP_KEY if isinstance(model_name, str) else None
    model_name = getattr(getattr(parent, "class_", None), "__name__", None)
    if not isinstance(model_name, str):
        return None
    identity = f"{model_name}.{key}"
    sites = _relationship_sites.get(tag)
    if sites is None or identity not in sites:
        with _lock:
            sites = _relationship_sites.setdefault(tag, {})
            if identity not in sites:
                sites[identity] = _first_application_location() or _declared_outside(prop, identity)
    collection = direction in {"ONETOMANY", "MANYTOMANY"}
    return identity, collection


def _batched_query(context: Any) -> str:
    """``select(Model).where(Model.attr.in_(ids))`` for an ORM SELECT filtered by one equality, else a generic hint."""
    try:
        compiled = context.compiled
        where = compiled.statement.whereclause
        if where.operator is operator.eq:
            mapper = compiled.compile_state._primary_entity.mapper  # noqa: SLF001
            name = mapper.class_.__name__
            return f"select({name}).where({name}.{mapper.get_property_by_column(where.left).key}.in_(ids))"
    except Exception:  # noqa: BLE001, S110 - introspection is defensive: a text or Core statement has no entity
        pass
    return GENERIC_BATCH


def _record_statement_site(context: Any, tag: tuple[str, int, str], key: tuple[str, Dialect]) -> None:
    """Remember where a repeated statement runs from in application code (its first repeat), and how to batch it."""
    sites = _statement_sites.get(tag)
    if sites is None or key not in sites:
        if sites is None or len(sites) < MAX_STATEMENT_SITES:
            with _lock:
                _statement_sites.setdefault(tag, {}).setdefault(key, None)
        return
    if sites[key] is not None:
        return
    site = (_first_application_location(), _batched_query(context))
    with _lock:
        if sites.get(key) is None:
            sites[key] = site


def _lazy_key(context: Any, statement: str) -> tuple[Any, Any, str] | None:
    """What a lazy load's observation depends on, or None for anything else (counted per execution, or not cached)."""
    options = getattr(context, "execution_options", None)
    if not options or RELATIONSHIP_KEY in options:
        return None
    parent = getattr(options.get("_sa_orm_load_options"), "_lazy_loaded_from", None)
    compiled = getattr(context, "compiled", None)
    if parent is None or compiled is None:
        return None
    return compiled, getattr(parent, "class_", None), statement


def _record_relationship(context: Any) -> None:  # pyright: ignore[reportUnusedFunction] - listeners calls it
    """Record relationship loads using SQLAlchemy's compiled execution context, without an ORM hook."""
    tag = TEST.get()
    if tag is None or tag[2] != "call":
        return
    statement = getattr(context, "statement", None)
    if not isinstance(statement, str):
        return
    dialect = _dialect_of(context)
    seen_key = _lazy_key(context, statement)
    if seen_key is None:  # a lazy load gets its site and fix from the relationship instead
        _record_statement_site(context, tag, (statement, dialect))
    if seen_key is not None:
        seen = _lazy_seen.get(tag)
        if seen is not None and seen_key in seen:
            return
    relation_value = _relationship_observation(context, tag)
    if seen_key is not None:
        with _lock:
            _lazy_seen.setdefault(tag, set()).add(seen_key)
    if isinstance(relation_value, tuple) and len(cast("tuple[object, ...]", relation_value)) == 2:
        _store_lazy_group(tag, statement, cast("tuple[object, object]", relation_value), dialect)
    elif relation_value is _EAGER_RELATIONSHIP_KEY:
        _count_eager_batch(tag, statement, dialect)


def _store_lazy_group(
    tag: tuple[str, int, str], statement: str, relation: tuple[object, object], dialect: Dialect
) -> None:
    """Remember which relationship a lazy-load statement belongs to (first observation wins)."""
    identity, collection = relation
    if not isinstance(identity, str) or not isinstance(collection, bool):
        return
    key = _masked_fingerprint(statement, dialect)
    if key is None:
        return
    groups = _relationship_groups.get(tag)
    if groups is None or key not in groups:
        with _lock:
            _relationship_groups.setdefault(tag, {}).setdefault(key, (identity, collection))


def _count_eager_batch(tag: tuple[str, int, str], statement: str, dialect: Dialect) -> None:
    """Count one eager-load batch statement, so it is not mistaken for an N+1 repeat."""
    key = _masked_fingerprint(statement, dialect)
    if key is None:
        return
    with _lock:
        batches = _eager_relationship_batches.setdefault(tag, {})
        batches[key] = batches.get(key, 0) + 1


def apply_relationship_facts(test: Any) -> None:
    """Move one test attempt's relationship observations into its serializable phase facts."""
    tag = (test.key.node_id, test.key.attempt, "call")
    with _lock:
        groups = _relationship_groups.pop(tag, {})
        sites = _relationship_sites.pop(tag, {})
        eager_batches = _eager_relationship_batches.pop(tag, {})
        _lazy_seen.pop(tag, None)
        statement_sites = _statement_sites.pop(tag, {})
    if not groups and not eager_batches and not statement_sites:
        return
    phase = test.phases.get("call")
    if phase is None:
        return
    for group, count in eager_batches.items():
        remaining = phase.selects.get(group, 0) - count
        if remaining > 0:
            phase.selects[group] = remaining
        else:
            phase.selects.pop(group, None)
            phase.sql_of.pop(group, None)
    phase.relationship_of.update(groups)
    phase.relationship_sites.update(sites)
    for group, (identity, _collection) in groups.items():
        count = phase.selects.get(group, 0)
        if count:
            phase.relationship_loads[identity] = phase.relationship_loads.get(identity, 0) + count
    for (statement, dialect), site in statement_sites.items():
        group = _masked_fingerprint(statement, dialect)
        if (
            group is not None
            and site is not None
            and phase.selects.get(group, 0) > 1
            and group not in phase.relationship_of
        ):
            phase.statement_sites.setdefault(group, site)


def _is_primary_mapper_load(target: Any, context: Any) -> bool:
    options = getattr(context, "load_options", None)
    if getattr(options, "_lazy_loaded_from", None) is not None:
        return False
    if getattr(options, "_sa_top_level_orm_context", None) is not None:
        return False
    primary = getattr(getattr(context, "compile_state", None), "_primary_entity", None)
    primary_class = getattr(getattr(primary, "mapper", None), "class_", None)
    return not isinstance(primary_class, type) or isinstance(target, primary_class)


def _unbounded_read_statement_shape(context: Any, statement_obj: Any) -> tuple[str, bool]:
    compiled_statement = getattr(getattr(context, "compiled", None), "statement", statement_obj)
    try:
        has_limit = (
            getattr(compiled_statement, "_limit_clause", None) is not None
            or getattr(compiled_statement, "_fetch_clause", None) is not None
        )
    except Exception:
        has_limit = True
    from sharpit.engine.capture.statement import masked_shape

    owner = context
    if getattr(context, "dialect", None) is None:
        session = getattr(context, "session", None)
        primary = getattr(getattr(context, "compile_state", None), "_primary_entity", None)
        mapper = getattr(primary, "mapper", None)
        try:
            owner = getattr(context, "bind_arguments", {}).get("bind") or (
                session.get_bind(mapper=mapper)
                if session is not None and mapper is not None
                else getattr(session, "bind", None)
            )
        except Exception:
            owner = None
    dialect = _dialect_of(owner)
    return masked_shape(_relationship_masker(), str(statement_obj), dialect).sql, has_limit


def _record_unbounded_read_load(target: Any, context: Any, info: Any, tag: tuple[str, int, str]) -> None:
    paging = info.paging
    if paging is None:
        paging = paging_of(info.scope)
        info.paging = paging
    if paging is None or paging.page_size is None or not _is_primary_mapper_load(target, context):
        return
    statement_obj = getattr(context, "query", None)
    if statement_obj is None:
        return
    entity = type(target).__name__
    with _lock:
        current = info.loads.setdefault(context, {}).setdefault(entity, {})
        current["loaded"] = cast(int, current.get("loaded", 0)) + 1
        fact = current.get("fact")
        if fact is not None:
            fact.loaded = cast(int, current["loaded"])
            return
        if current.get("shape_attempted"):
            return
        if current["loaded"] < paging.page_size * _unbounded_read_factor:
            return
        current["shape_attempted"] = True
        statement, has_limit = _unbounded_read_statement_shape(context, statement_obj)
        row_key = f"{info.id}:{id(context)}:{entity}"
        fact = UnboundedReadFact(
            paging.route,
            statement,
            entity,
            cast(int, current["loaded"]),
            paging.page_size,
            has_limit,
            _first_application_location(),
        )
        current["fact"] = fact
        _unbounded_read_facts.setdefault(tag, {})[row_key] = fact


def _mapper_load(target: Any, context: Any) -> None:  # pyright: ignore[reportUnusedFunction] - listeners calls it
    global _unbounded_read_capture_missing  # noqa: PLW0603
    try:
        info = REQUEST.get()
        tag = TEST.get()
        if tag is None or tag[2] != "call":
            return
        if info is None or info.scope is None:
            missing_capture_key = tag[:2]
            if missing_capture_key not in _unbounded_read_missing_capture:
                with _lock:
                    if missing_capture_key not in _unbounded_read_missing_capture:
                        _unbounded_read_missing_capture.add(missing_capture_key)
                        _unbounded_read_capture_missing = True
            return
        _record_unbounded_read_load(target, context, info, tag)
    except Exception as exc:  # noqa: BLE001 - a diagnostic listener never changes a query result
        dispatch.routing_failed(exc)


def apply_unbounded_read_facts(test: Any) -> bool:
    tag = (test.key.node_id, test.key.attempt, "call")
    with _lock:
        facts = _unbounded_read_facts.pop(tag, {})
        missing_capture = tag[:2] in _unbounded_read_missing_capture
        _unbounded_read_missing_capture.discard(tag[:2])
    if facts:
        test.phases.setdefault("call", PhaseFacts())
        test.phases["call"].unbounded_reads.extend(facts.values())
    return missing_capture


def unbounded_read_capture_limitation_needed() -> bool:
    with _lock:
        return _unbounded_read_capture_missing and not _unbounded_read_request_seen


def set_identity_key(key: bytes | None) -> None:
    """The session's key: this group must be the sink's, and on SQLite only the key says which group that is."""
    _relationship_masker().identity_key = key
    _masked_fingerprint.cache_clear()


def set_unbounded_read_factor(factor: int) -> None:
    global _unbounded_read_factor  # noqa: PLW0603
    with _lock:
        _unbounded_read_factor = factor
