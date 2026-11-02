# A-data docs (merged into README / skills/sharpit/SKILL.md by the coordinator)

SKILL table row:

| Panel | What it shows | Needs |
|---|---|---|
| `data` | SQLAlchemy mapped classes: table, primary-key type, relationships (once the app's first query has configured the mappers). Never configures mappers or runs SQL. MCP: `get_data_repositories`. | `install(app, models=Base)`; SQLAlchemy 2.0+ |

```python
import sharpit

sharpit.install(app, models=Base)  # a declarative base, a registry, or a list of them or of mapped classes
```

Before the app runs its first query the rows are listed with `relationships: null` and the reason
"Mappers are not configured yet: the app has not run a query".
