from sharpit.engine.collectors.data import repositories_report
from sharpit.engine.tools import Tool

TOOLS = (
    Tool(
        "get_data_repositories",
        "Return the SQLAlchemy mapped classes passed to install(models=...) with their table, primary-key type and, "
        "once the application has configured its mappers, their relationships. Never configures mappers or runs SQL.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "data",
        False,
        lambda c, a: repositories_report(c.ctx),
    ),
)
COMMANDS = {"get_data_repositories": "data repositories"}
