"""Java Agent reads have no side effects, and the panel gates its read, its sensor switch and its CLI actions."""

PANEL = "java-agent"
GET_ROWS = ["/sharpit/api/java-agent"]
WRITE_ROWS = [("POST", "/sharpit/api/java-agent/sensors/{sensor}")]
PATH_PARAMS = {"sensor": "files"}
CLI_ACTIONS = ["enable_agent_sensor", "disable_agent_sensor"]
