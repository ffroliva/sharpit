"""design/tokens.css is the one source of the console's colour and spacing tokens; design/DESIGN.md documents it."""

import math
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOKENS = ROOT / "design" / "tokens.css"
DOC = ROOT / "design" / "DESIGN.md"
UI_SRC = ROOT / "ui" / "src"

LIGHT = ':root, [data-md-color-scheme="default"]'
DARK = ':root[data-theme="dark"], [data-md-color-scheme="slate"]'
SELECTORS = (
    LIGHT,
    ':root:not([data-theme="light"])',
    ':root[data-theme="light"]',
    DARK,
)
DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _text() -> str:
    assert TOKENS.is_file(), "design/tokens.css does not exist"
    return TOKENS.read_text(encoding="utf-8")


def tokens(theme: str) -> dict[str, str]:
    """The token values of a theme, read from design/tokens.css."""
    selector = {"light": LIGHT, "dark": DARK}[theme]
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", _text(), re.DOTALL)
    assert block, f"no block for {selector}"
    return {name.removeprefix("--"): value.strip() for name, value in DECL.findall(block.group(1))}


def _oklch_to_linear_srgb(value: str) -> tuple[float, float, float]:
    lightness, chroma, hue = (float(x) for x in re.fullmatch(r"oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)", value).groups())  # type: ignore[union-attr]
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    return tuple(min(1.0, max(0.0, c)) for c in rgb)  # type: ignore[return-value]


def _luminance(value: str) -> float:
    r, g, b = _oklch_to_linear_srgb(value)

    # WCAG 2 relative luminance is defined on gamma-encoded sRGB, so encode then decode with the WCAG curve
    def encode(c: float) -> float:
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    def decode(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (decode(encode(c)) for c in (r, g, b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG 2 contrast ratio of two OKLCH colours."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _doc_tables() -> list[list[list[str]]]:
    """Rows (cells) of every table under a `##` heading whose title contains "tokens"."""
    tables: list[list[list[str]]] = []
    in_section, in_table = False, False
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_section = "tokens" in line.lower()
        is_row = in_section and line.startswith("|")
        if is_row:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not in_table:
                tables.append([])
            if not set("".join(cells)) <= set("-: "):
                tables[-1].append(cells)
        in_table = is_row
    return tables


def contrast_pairs() -> list[tuple[str, str]]:
    """(text, surface) token pairs from the Colour tokens table of design/DESIGN.md."""
    pairs: list[tuple[str, str]] = []
    for table in _doc_tables():
        for cells in table[1:]:
            name = cells[0].strip("`").removeprefix("--")
            measured = cells[-1] if len(cells) >= 5 else ""
            if "/" in measured:
                pairs += [(name, surface) for surface in ("bg", "rail", "sel")]
            elif name == "on-accent":
                pairs.append((name, "accent"))
    return pairs


@pytest.fixture(params=["light", "dark"])
def theme(request: pytest.FixtureRequest) -> str:
    return request.param


def test_contrast_matches_the_measured_table() -> None:
    light, dark = tokens("light"), tokens("dark")
    assert round(contrast(light["ink"], light["bg"]), 1) == 17.3
    assert round(contrast(light["muted"], light["bg"]), 1) == 6.5
    assert round(contrast(dark["ink"], dark["bg"]), 1) == 15.6
    assert round(contrast(dark["accent"], dark["bg"]), 1) == 9.3


def test_text_pairs_pass_aa(theme: str) -> None:
    values = tokens(theme)
    pairs = contrast_pairs()
    assert len(pairs) >= 19, "the doc table lost its contrast pairs"
    for text, surface in pairs:
        assert contrast(values[text], values[surface]) >= 4.5, (text, surface)


def test_built_css_carries_the_tokens() -> None:
    _text()
    built = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "src/sharpit/ui/static/assets").glob("*.css"))
    assert "--accent:" in built
    assert "data-md-color-scheme" in built  # absent until the rebuild, so this is a real red


def test_console_defines_no_token() -> None:
    names = {n for n, _ in DECL.findall(_text())}
    declared = {n for n, _ in DECL.findall((UI_SRC / "app.css").read_text(encoding="utf-8"))}
    assert not names & declared


def test_no_colour_fallbacks_in_ui() -> None:
    _text()
    hits = [
        str(p.relative_to(ROOT))
        for p in UI_SRC.rglob("*")
        if p.suffix in {".svelte", ".ts", ".css"} and re.search(r"var\(--[a-z-]+,", p.read_text(encoding="utf-8"))
    ]
    assert hits == []


def test_doc_lists_every_token() -> None:
    names = {n for n, _ in DECL.findall(_text())}
    documented = {
        cells[0].strip("`") for table in _doc_tables() for cells in table[1:] if cells[0].strip("`").startswith("--")
    }
    assert documented == names


def test_theme_blocks_survive() -> None:
    text = _text()
    for selector in SELECTORS:
        assert selector + " {" in text, selector


def test_reduced_motion_survives() -> None:
    text = _text()
    assert "@media (prefers-reduced-motion: reduce)" in text
    assert "--dur: 0ms" in text


def test_sdist_excludes_design() -> None:
    _text()
    exclude = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"][
        "sdist"
    ]["exclude"]
    assert "/design" in exclude
    assert "/tests/design" in exclude
