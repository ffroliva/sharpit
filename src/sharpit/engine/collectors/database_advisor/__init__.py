"""The ``database-advisor`` panel (0.5.0 spec §5.8): the rule registration list, in report order."""

from __future__ import annotations

from sharpit.engine.collectors.database_advisor import rules_driver_pool, rules_orm, rules_schema

RULES = (*rules_schema.RULES, *rules_orm.RULES, *rules_driver_pool.RULES)
