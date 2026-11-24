"""List, read, and search the installed documentation without a server."""

import json
from typing import TextIO

from sharpit import __version__
from sharpit.cli.docs_catalog import TOPICS, read_page
from sharpit.cli.render import write, write_utf8


def _search(query: str) -> list[dict[str, str | int]]:
    if not query.strip():
        raise ValueError("--search must not be blank.")
    needle = query.lower()
    matches: list[dict[str, str | int]] = []
    for topic, (file, _, _) in TOPICS.items():
        lines = read_page(file).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for number, line in enumerate(lines, 1):
            if needle in line.lower():
                matches.append({"topic": topic, "file": file, "line": number, "text": line})
    return matches


def show_docs(topic: str | None, search: str | None, out: TextIO, *, json_output: bool, terminal: bool) -> None:
    if topic is not None and search is not None:
        raise ValueError("Choose a topic or --search, not both.")

    result: dict[str, object] = {"version": __version__}
    if search is not None:
        matches = _search(search)
        result.update(query=search, matches=matches)
        text = "".join(f"{match['file']}:{match['line']}:{match['text']}\n" for match in matches)
    elif topic is not None:
        page = TOPICS.get(topic)
        if page is None:
            raise ValueError(f"Unknown documentation topic: {topic}. Run 'sharpit docs' to list topics.")
        file, _, _ = page
        text = read_page(file)
        result.update(topic=topic, file=file, content=text)
    else:
        result["topics"] = [
            {"id": key, "title": title, "description": description, "file": file}
            for key, (file, title, description) in TOPICS.items()
        ]
        text = f"Bundled documentation for sharpit {__version__}:\n" + "".join(
            f"{key} - {description}\n" for key, (_, _, description) in TOPICS.items()
        )
    if json_output:
        write_utf8(out, json.dumps(result) + "\n")
    else:
        (write if terminal else write_utf8)(out, text)
    out.flush()
