"""Static checks for the console's documented type and spacing rules."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI_SRC = ROOT / "ui" / "src"
PUBLISHED_SIZES = {"11px", "12px", "12.5px", "13px", "14.5px", "16.5px", "20px"}


def svelte_files() -> list[Path]:
    files = list(UI_SRC.rglob("*.svelte"))
    assert files, "no Svelte files found under ui/src"
    return files


def svelte_matches(pattern: str) -> list[str]:
    matches = [
        str(path.relative_to(UI_SRC)) for path in svelte_files() if re.search(pattern, path.read_text(encoding="utf-8"))
    ]
    return matches


def css_files() -> list[Path]:
    files = [*UI_SRC.rglob("*.css"), *svelte_files()]
    assert files, "no UI CSS or Svelte files found under ui/src"
    return files


def css_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in css_files())


def css_font_sizes() -> set[str]:
    declarations = re.findall(r"\bfont(?:-size)?\s*:\s*([^;}]+)", css_text())
    sizes = {match.group(1) for declaration in declarations if (match := re.search(r"\b([\d.]+px)", declaration))}
    assert sizes, "no font sizes found under ui/src"
    return sizes


def uncommented_off_scale_spacing() -> list[str]:
    failures = []
    for path in css_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code, _, comment = line.partition("/*")
            for match in re.finditer(r"(?:margin|padding|gap)(?:-[a-z]+)?\s*:[^;}]*", code):
                sizes = [abs(float(size)) for size in re.findall(r"(?<![\w.])(-?\d+(?:\.\d+)?)px", match.group())]
                if any(
                    size > 3 or 0 < size < 1 or 1 <= size <= 3 and not comment.strip().endswith("*/") for size in sizes
                ):
                    failures.append(f"{path.relative_to(ROOT)}:{line_number}: {match.group().strip()}")
    return failures


def test_console_uses_h1_and_h2_only():
    assert not svelte_matches(r"<h[3-6]\b")


def test_no_card_rule_in_the_console():
    assert not svelte_matches(r"\.card\b")


def test_font_sizes_are_published():
    assert css_font_sizes() <= PUBLISHED_SIZES


def test_spacing_literals_are_commented():
    assert uncommented_off_scale_spacing() == []
