"""The explicit catalog of user guides and decisions shipped with sharpit."""

from importlib import resources
from os import path

# In display order, each entry holds the repository path, title and description.
# The wheel build hook reads this literal without importing sharpit.
TOPICS = {
    "index": ("website/docs/index.md", "sharpit", "Project overview and links to get started"),
    "installation": ("website/docs/installation.md", "Installation", "Installation options and optional dependencies"),
    "quickstart": ("website/docs/quickstart.md", "Quickstart", "Mount and open the developer console"),
    "activation": ("website/docs/activation.md", "Activation", "Profiles, activation modes, and development signals"),
    "panels": ("website/docs/panels.md", "Panels", "Available console panels and their capabilities"),
    "sql-sources": ("website/docs/sql-sources.md", "SQL sources", "Register and inspect SQL sources"),
    "pytest-plugin": ("website/docs/pytest-plugin.md", "Pytest plugin", "Run application checks from a test suite"),
    "report": ("website/docs/report.md", "Test report", "Read and use the pytest plugin's report"),
    "mcp": ("website/docs/mcp.md", "MCP for AI agents", "Connect to the MCP server and discover its tools"),
    "cli": ("website/docs/cli.md", "Command-Line Client", "CLI installation, commands, output, and exit codes"),
    "ai-agents": ("website/docs/ai-agents.md", "AI agents", "Agent skills, MCP tools, and diagnostic workflows"),
    "settings": ("website/docs/settings.md", "Settings", "Configuration settings and defaults"),
    "safety": ("website/docs/safety.md", "Safety model", "Access controls, masking, and read-only behavior"),
    "how-it-works": ("website/docs/how-it-works.md", "How sharpit works", "Architecture and runtime behavior"),
    "deviations": ("website/docs/deviations.md", "Deviations from BootUI", "Intentional differences from BootUI"),
    "decisions": ("docs/decisions/README.md", "Design decisions", "Index of sharpit's design decisions"),
    "decision-activation-signals": (
        "docs/decisions/activation-signals.md",
        "Activation signals",
        "Activation precedence and recognition of reloading development servers",
    ),
    "decision-baseline-owner": (
        "docs/decisions/baseline-owner.md",
        "Baseline entry owner",
        "When a baselined test-runtime finding is reported fixed or inconclusive",
    ),
    "decision-wsgi-request-target": (
        "docs/decisions/wsgi-request-target.md",
        "WSGI request target validation",
        "Validation of original request targets and the WSGI Host header",
    ),
    "decision-003-request-values-in-memory": (
        "docs/decisions/003-request-values-in-memory.md",
        "Request values in memory",
        "Bounded request-lifetime matching for command and file path sinks",
    ),
}


def read_page(file: str) -> str:
    """Read a catalog path from package resources or the editable source tree."""
    bundled = resources.files("sharpit").joinpath("_docs")
    src = path.dirname(path.dirname(path.dirname(path.abspath(__file__))))
    checkout = path.dirname(src)
    try:
        # Only a sharpit source checkout (marked by its build hook) may stand in for the bundled pages.
        if (
            not bundled.is_dir()
            and path.basename(src) == "src"
            and path.isfile(path.join(checkout, "hatch_build.py"))
            and path.isfile(path.join(checkout, "docs", "decisions", "README.md"))
        ):
            with open(path.join(checkout, file), "rb") as page:
                return page.read().decode("utf-8")
        return bundled.joinpath(*file.split("/")).read_bytes().decode("utf-8")
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Bundled documentation is missing: {file}") from error
