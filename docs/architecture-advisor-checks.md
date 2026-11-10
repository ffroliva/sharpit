# Architecture advisor checks

Heuristic, project-agnostic architecture rules running against the host application's own classes.

## Rules

| id | sev | title | description |
|---|---|---|---|
| ARCH-PKG-001 | HIGH | Packages should be free of cycles | Circular dependencies between packages make code difficult to understand, test, and maintain. |
| ARCH-MOD-001 | HIGH | Internal packages should not be accessed from other modules | Modules must not import private or internal modules from outside their parent package. |
| ARCH-CODE-001 | LOW | Classes should not access standard streams | Writing directly to standard streams bypasses logging configurations and formatting. |
| ARCH-CODE-002 | LOW | Classes should not throw generic exceptions | Raising generic Exception or BaseException obscures error causes and hinders specific error handling. |
| ARCH-CODE-004 | INFO | Classes should not use Joda-Time | Legacy third-party timezone libraries such as pytz are superseded by the standard zoneinfo module. |
| ARCH-CODE-006 | HIGH | Classes should not forcibly terminate the JVM | Application classes outside entry points should not call sys.exit, os._exit, exit, or quit. |
| ARCH-CODE-007 | MEDIUM | Classes should not access JDK-internal APIs | Importing private symbols from third-party libraries creates brittle dependencies on internal implementation details. |
| ARCH-CODE-008 | INFO | Classes should not use legacy date and time classes | datetime.utcnow() and utcfromtimestamp() are deprecated in Python 3.12. |
| ARCH-CODE-009 | INFO | Classes should not use deprecated APIs | Calls to Python application functions or classes marked with PEP 702 deprecated decorators should be replaced. |
| ARCH-CODE-010 | INFO | Exceptions should be named ending with Exception | PEP 8 recommends naming exception classes with an Error or Exception suffix. |
| ARCH-CODE-012 | LOW | Loggers should be private final or container-managed | Loggers should be acquired using logging.getLogger(__name__) to maintain proper hierarchy. |
| ARCH-CODE-013 | MEDIUM | Application classes should not depend on test frameworks | Production application code must not import test libraries such as pytest, unittest.mock, or hypothesis. |
| ARCH-CODE-014 | MEDIUM | Classes should not have public mutable static fields | Functions rebinding module-level globals introduce mutable shared state and concurrency hazards. |
| ARCH-CODE-017 | MEDIUM | Classes should not directly instantiate Thread | Directly creating threading.Thread instances bypasses concurrency limits and thread pools. |
| ARCH-CODE-018 | INFO | Assertions should have a detail message | Assertions in production code without messages provide unhelpful traceback diagnostics and may be stripped under -O. |
| ARCH-SPRING-002 | LOW | Controllers should not depend on repositories | Route handlers and controllers should access data through service layers rather than repositories directly. |
| ARCH-SPRING-003 | MEDIUM | Repositories should not depend on controllers | Data repositories must not import or depend on controller or router modules. |
| ARCH-SPRING-006 | MEDIUM | Services should not depend on controllers | Business services must not depend on controller or web presentation modules. |
| ARCH-SPRING-007 | MEDIUM | Repositories should not depend on services | Data access repositories should not depend on higher-level service layer modules. |
| ARCH-SPRING-008 | MEDIUM | Services and repositories should not depend on web request types | Domain services and repositories should be transport-agnostic and not import Request or Response objects. |
| ARCH-SPRING-015 | INFO | Configuration properties classes should be immutable | Pydantic BaseSettings fields should use immutable configuration so application settings cannot be changed after loading. |
| ARCH-PY-001 | HIGH | Packages should respect declared import-linter contracts | Module dependencies violate architectural layering or forbidden import contracts declared in pyproject.toml. |
