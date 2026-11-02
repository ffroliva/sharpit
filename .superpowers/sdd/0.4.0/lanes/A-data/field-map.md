# A-data field map

| BootUI key | Python source |
|---|---|
| `springDataPresent` | `True` when `models=` resolves to at least one registry and SQLAlchemy 2+ is imported |
| `total` | `len(repositories)` |
| `beanName` | class `__qualname__` |
| `repositoryInterface`, `domainType` | `f"{cls.__module__}.{cls.__qualname__}"` |
| `idType` | primary-key column type names joined by ", "; `null` if none |
| `storeModule` | `"SQLAlchemy"` |
| `customImplementation` | `null` (no analogue) |
| `queryMethodCount`, `fragmentCount` | `null` (nullable.json: SQLAlchemy has no repository methods or fragments) |
| detail `methods[].origin` | `"APPLICATION"` (one row per relationship, spec §7) |
| extra `table`, `relationships`, `unavailableReason`, `warnings` | sharpit additions (spec §11 log) |
