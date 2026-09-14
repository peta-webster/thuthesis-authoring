#!/usr/bin/env python3
"""Extract a compact outline and LaTeX object summary from a .tex file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _shared_patterns import CITE_RE, prepare_active_tex

HEADING_RE = re.compile(
    r"\\(chapter|section|subsection|subsubsection)\*?\{((?:[^{}]|\{[^{}]*\})*)\}"
)
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
ENV_RE = re.compile(r"\\begin\{(figure|table|equation|align|gather|algorithm|lstlisting)\*?\}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tex_file")
    args = parser.parse_args()

    path = Path(args.tex_file)
    try:
        text = prepare_active_tex(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        print(json.dumps({"file": str(path), "error": f"not valid UTF-8: {exc}"}, ensure_ascii=False, indent=2))
        return 1
    except OSError as exc:
        print(json.dumps({"file": str(path), "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    headings = [
        {"level": match.group(1), "title": match.group(2), "line": text[: match.start()].count("\n") + 1}
        for match in HEADING_RE.finditer(text)
    ]
    cites = sorted({key.strip() for match in CITE_RE.finditer(text) for key in match.group(1).split(",")})
    envs: dict[str, int] = {}
    for match in ENV_RE.finditer(text):
        envs[match.group(1)] = envs.get(match.group(1), 0) + 1

    result = {
        "file": str(path),
        "headings": headings,
        "labels": sorted(set(LABEL_RE.findall(text))),
        "citations": cites,
        "environments": envs,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
