#!/usr/bin/env python3
"""Extract source material (.docx / .md / .txt) into a normalized JSON outline.

This is the ingestion front end for the skill: it turns a user's raw material
into headings, paragraphs, and an explicit list of things that must not be
auto-converted, so the model can do the chapter mapping without ever guessing
at binary content.

Word files are read with Pandoc when it is available, which is the higher
fidelity path and matches how the wider skill ecosystem reads .docx. When
Pandoc is missing the script falls back to parsing the OOXML directly with the
standard library: lower fidelity, but it still recovers heading levels and
paragraph text rather than failing outright. The chosen path is always
reported in `extractor`.

The extractor distinguishes deterministic native Markdown objects from source
objects whose semantics cannot be recovered safely. Balanced Markdown math is
summarized for review and valid pipe tables become conversion candidates;
Word/OMML objects and malformed Markdown remain under `manual_review` so the
caller can emit visible TODO markers instead of silently guessing.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Optional

from _markdown_syntax import markdown_fenced_lines, scan_markdown_math, scan_pipe_tables
from _subprocess_safety import run_captured

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
COMMON_BIN_DIRS = [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]

HEADING_STYLE_RE = re.compile(r"^heading\s*(\d)$|^h(\d)$|^标题\s*(\d)$", re.I)
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
MD_FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\]")
NUMERIC_MARKER_RE = re.compile(r"(?<!\\)[\[［【]\s*([0-9０-９][0-9０-９\s,，、;；\-－–—~～至]*)\s*[\]］】]")
FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_DOCX_XML_BYTES = 100 * 1024 * 1024


def q(tag: str, ns: str = W) -> str:
    return f"{{{ns}}}{tag}"


def find_pandoc() -> Optional[str]:
    found = shutil.which("pandoc")
    if found:
        return found
    for directory in COMMON_BIN_DIRS:
        candidate = directory / "pandoc"
        if candidate.exists():
            return str(candidate)
    return None


def heading_level_from_style(value: str) -> Optional[int]:
    match = HEADING_STYLE_RE.match(value.strip())
    if not match:
        return None
    digit = next((g for g in match.groups() if g), None)
    return int(digit) if digit else None


def collect_numeric_markers(text: str) -> list[int]:
    numbers: list[int] = []
    for match in NUMERIC_MARKER_RE.finditer(text):
        for token in re.split(r"[,，、;；]", match.group(1).translate(FULLWIDTH_DIGITS)):
            token = token.strip()
            if token.isdigit():
                numbers.append(int(token))
            else:
                span = re.fullmatch(r"(\d+)\s*(?:-|－|–|—|~|～|至)\s*(\d+)", token)
                if span:
                    start, end = int(span.group(1)), int(span.group(2))
                    if 0 < end - start < 100:
                        numbers.extend(range(start, end + 1))
    return numbers


# --- Markdown path (also used for Pandoc output) -------------------------


def _manual_review_item(
    item_type: str,
    message: str,
    reason_code: str,
    recommended_tool: str,
    *,
    line: Optional[int] = None,
    end_line: Optional[int] = None,
    **extra: object,
) -> dict:
    item = {
        "type": item_type,
        "message": message,
        "requires_todo": True,
        "reason_code": reason_code,
        "start_line": line,
        "end_line": end_line if end_line is not None else line,
        "recommended_tool": recommended_tool,
    }
    if line is not None:
        # Keep the v1 location field for callers that have not migrated yet.
        item["line"] = line
    item.update(extra)
    return item


def _normalize_manual_review(items: list[dict]) -> list[dict]:
    """Add schema-v2 fields without removing any v1 fields."""
    defaults = {
        "table": ("table_requires_review", "scripts/convert_markdown_tables.py"),
        "equation": ("equation_requires_review", "scripts/escape_latex_text.py --math-aware"),
        "image": ("image_asset_requires_review", "manual image extraction"),
        "footnote": ("footnote_requires_review", "manual footnote conversion"),
        "endnote": ("endnote_requires_review", "manual endnote conversion"),
    }
    normalized: list[dict] = []
    for original in items:
        item = dict(original)
        reason_code, tool = defaults.get(item.get("type", ""), ("source_object_requires_review", "manual review"))
        line = item.get("line")
        item.setdefault("requires_todo", True)
        item.setdefault("reason_code", reason_code)
        item.setdefault("start_line", line if isinstance(line, int) else None)
        item.setdefault("end_line", line if isinstance(line, int) else None)
        item.setdefault("recommended_tool", tool)
        normalized.append(item)
    return normalized


def _math_summary(text: str) -> tuple[dict, list]:
    spans, issues = scan_markdown_math(text)
    inline_count = sum(span.kind == "inline" for span in spans)
    display_count = sum(span.kind == "display" for span in spans)
    return ({
        "inline_count": inline_count,
        "display_count": display_count,
        "total_count": inline_count + display_count,
        "spans": [span.as_dict() for span in spans],
        "unclosed": [issue.as_dict() for issue in issues],
    }, spans)


def _looks_like_literal_price(text: str, issue: dict) -> bool:
    """Distinguish common ``$5`` prose prices from unclosed math syntax."""
    fragment = text[issue["start_offset"]:issue["end_offset"]]
    amount = re.match(
        r"^\$(?:[A-Z]{3}\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?",
        fragment,
    )
    if not amount:
        return False
    remainder = fragment[amount.end():]
    if not remainder:
        return True

    # A price token needs a prose boundary.  Immediate TeX/math syntax is an
    # unclosed equation even when the expression starts with a number.
    prose_boundaries = "，。；;、,:：.!?！？）)]元美元"
    if not (remainder[0].isspace() or remainder[0] in prose_boundaries):
        return False
    context = remainder.lstrip(" \t\r\n" + prose_boundaries)
    if not context:
        return True
    return not bool(re.match(
        r"^(?:[+\-*/^_=<>]|\\(?:frac|sqrt|times|cdot|left|right)\b)",
        context,
    ))


def analyze_markdown(text: str, source_kind: str = "markdown") -> dict:
    """Return schema-v2 Markdown analysis while preserving v1 block shapes.

    ``source_kind='pandoc-docx'`` is intentionally conservative: pipe tables
    and dollar math produced from a Word document remain manual-review objects
    because merged cells and OMML semantics cannot be proven from Pandoc's
    flattened Markdown alone.
    """
    blocks: list[dict] = []
    manual: list[dict] = []
    conversion_candidates: list[dict] = []
    review_advisories: list[dict] = []
    lines = text.splitlines()
    fenced_lines = markdown_fenced_lines(text)
    tables = scan_pipe_tables(text)
    table_by_start = {table.start_index: table for table in tables}
    footnote_definitions: dict[str, dict[str, object]] = {}
    footnote_definition_lines: set[int] = set()

    # Pandoc serializes DOCX footnotes as Markdown definitions. Keep their
    # source text for manual review, but do not expose the definitions as body
    # paragraphs that could be copied into LaTeX unchanged.
    index = 0
    while index < len(lines):
        if index in fenced_lines:
            index += 1
            continue
        match = MD_FOOTNOTE_DEF_RE.match(lines[index])
        if not match:
            index += 1
            continue
        label = match.group(1)
        parts = [match.group(2).strip()]
        footnote_definition_lines.add(index)
        cursor = index + 1
        while cursor < len(lines):
            continuation = lines[cursor]
            if continuation.startswith(("    ", "\t")):
                parts.append(continuation.strip())
                footnote_definition_lines.add(cursor)
                cursor += 1
                continue
            if not continuation.strip() and cursor + 1 < len(lines) and lines[cursor + 1].startswith(("    ", "\t")):
                footnote_definition_lines.add(cursor)
                cursor += 1
                continue
            break
        footnote_definitions.setdefault(label, {
            "line": index + 1,
            "text": " ".join(part for part in parts if part),
        })
        index = cursor

    reported_footnotes: set[str] = set()

    index = 0
    while index < len(lines):
        line_no = index + 1
        raw = lines[index]
        if index in footnote_definition_lines:
            index += 1
            continue
        line = raw.rstrip()
        stripped = line.strip()

        if index in fenced_lines:
            index += 1
            continue

        table = table_by_start.get(index)
        if table is not None:
            blocks.append({
                "type": "table",
                "text": table.source_text,
                "line": table.start_line,
                "start_line": table.start_line,
                "end_line": table.end_line,
            })
            if source_kind == "pandoc-docx":
                manual.append(_manual_review_item(
                    "table",
                    "Word 表格经 Pandoc 展平，需核对合并单元格和嵌套内容；请勿直接自动写入 LaTeX",
                    "word_table_requires_review",
                    "manual Word table review",
                    line=table.start_line,
                    end_line=table.end_line,
                    source_text=table.source_text,
                ))
            elif table.valid:
                conversion_candidates.append(table.as_candidate_dict())
            else:
                nested_object_reasons = {
                    "markdown_table_image_requires_review",
                    "markdown_table_footnote_requires_review",
                    "markdown_table_link_requires_review",
                    "markdown_table_reference_link_requires_review",
                    "markdown_table_html_requires_review",
                    "markdown_table_code_requires_review",
                    "markdown_table_emphasis_requires_review",
                }
                if table.reason_code in nested_object_reasons:
                    table_message = (
                        "Markdown 表格单元格含图片、脚注、链接、代码、强调或 HTML 对象；"
                        "已完整保留原文，需人工处理嵌套对象后再决定转换"
                    )
                    recommended_tool = "manual Markdown table object review"
                else:
                    table_message = "Markdown 表格结构不完整或列数不一致；已保留原文，需修正后再转换"
                    recommended_tool = "scripts/convert_markdown_tables.py"
                manual.append(_manual_review_item(
                    "table",
                    table_message,
                    table.reason_code,
                    recommended_tool,
                    line=table.start_line,
                    end_line=table.end_line,
                    source_text=table.source_text,
                ))
            index = table.end_index + 1
            continue

        if not stripped:
            index += 1
            continue

        heading = MD_HEADING_RE.match(line)
        if heading:
            blocks.append({
                "type": "heading",
                "level": len(heading.group(1)),
                "text": heading.group(2),
                "line": line_no,
            })
            index += 1
            continue

        if MD_IMAGE_RE.search(stripped):
            manual.append(_manual_review_item(
                "image",
                "图片需人工提供图源并撰写 caption",
                "markdown_image_asset_requires_review",
                "manual image asset review",
                line=line_no,
            ))

        for label in dict.fromkeys(MD_FOOTNOTE_REF_RE.findall(stripped)):
            if label in reported_footnotes:
                continue
            definition = footnote_definitions.get(label, {})
            manual.append(_manual_review_item(
                "footnote",
                "脚注/尾注需人工转写并核对引用位置；请勿自动写入 LaTeX 正文",
                "markdown_footnote_requires_review",
                "manual footnote conversion",
                line=line_no,
                label=label,
                text=definition.get("text", ""),
            ))
            reported_footnotes.add(label)

        blocks.append({
            "type": "list_item" if stripped.startswith(("- ", "* ", "+ ")) else "paragraph",
            "text": stripped,
            "line": line_no,
        })
        index += 1

    for label, definition in footnote_definitions.items():
        if label not in reported_footnotes:
            manual.append(_manual_review_item(
                "footnote",
                "脚注/尾注需人工转写并核对引用位置；请勿自动写入 LaTeX 正文",
                "markdown_footnote_requires_review",
                "manual footnote conversion",
                line=int(definition["line"]),
                label=label,
                text=definition["text"],
            ))

    detected_math, math_spans = _math_summary(text)
    if math_spans:
        review_advisories.append({
            "type": "math",
            "requires_todo": False,
            "reason_code": "balanced_markdown_math_detected",
            "inline_count": detected_math["inline_count"],
            "display_count": detected_math["display_count"],
            "message": "已按数学对象识别平衡的 Markdown 公式；转换后仍应抽样核对语义",
        })
    for issue in detected_math["unclosed"]:
        if _looks_like_literal_price(text, issue):
            review_advisories.append({
                "type": "literal_price",
                "requires_todo": False,
                "reason_code": "literal_dollar_price_detected",
                "start_line": issue["start_line"],
                "end_line": issue["end_line"],
                "message": "字面美元价格不会作为数学式保留，math-aware 转义会将其安全转义",
            })
        else:
            manual.append(_manual_review_item(
                "equation",
                "Markdown 数学定界符未闭合；需核对后再执行 math-aware 转义",
                "unclosed_markdown_math",
                "scripts/escape_latex_text.py --math-aware",
                line=issue["start_line"],
                end_line=issue["end_line"],
            ))

    if source_kind == "pandoc-docx":
        for span in math_spans:
            manual.append(_manual_review_item(
                "equation",
                "Word 公式经 Pandoc 转为美元数学式，仍需按对象核对 OMML 语义",
                "word_omml_equation_requires_review",
                "manual OMML-to-LaTeX review",
                line=span.start_line,
                end_line=span.end_line,
            ))

    return {
        "blocks": blocks,
        "manual_review": _normalize_manual_review(manual),
        "detected_math": detected_math,
        "conversion_candidates": conversion_candidates,
        "review_advisories": review_advisories,
    }


def parse_markdown(text: str) -> tuple[list[dict], list[dict]]:
    """Compatibility API returning the original two-list tuple."""
    analysis = analyze_markdown(text)
    return analysis["blocks"], analysis["manual_review"]


# --- DOCX stdlib fallback path ------------------------------------------


def paragraph_text(paragraph: ET.Element) -> tuple[str, bool, bool, list[tuple[str, str]]]:
    """Return text, object flags, and note references, skipping deletions."""
    parts: list[str] = []
    has_equation = paragraph.find(f".//{q('oMath', M)}") is not None
    has_image = paragraph.find(f".//{q('drawing')}") is not None
    note_references: list[tuple[str, str]] = []

    for run in paragraph.iter(q("r")):
        # A run inside <w:del> is text the author already deleted; including it
        # would resurrect removed content into the thesis.
        if any(run in list(deleted.iter()) for deleted in paragraph.iter(q("del"))):
            continue
        for kind, tag in (("footnote", "footnoteReference"), ("endnote", "endnoteReference")):
            note_references.extend((kind, node.get(q("id"), "")) for node in run.iter(q(tag)))
        for node in run.iter(q("t")):
            parts.append(node.text or "")
    return "".join(parts), has_equation, has_image, note_references


def read_note_parts(archive: zipfile.ZipFile, names: set[str]) -> dict[tuple[str, str], str]:
    notes: dict[tuple[str, str], str] = {}
    for kind, member, item_tag in (
        ("footnote", "word/footnotes.xml", "footnote"),
        ("endnote", "word/endnotes.xml", "endnote"),
    ):
        if member not in names:
            continue
        note_root = ET.fromstring(archive.read(member))
        for item in note_root.findall(q(item_tag)):
            note_id = item.get(q("id"), "")
            if not note_id or note_id.startswith("-"):
                continue
            value = "".join(node.text or "" for node in item.iter(q("t"))).strip()
            notes[(kind, note_id)] = value
    return notes


def parse_docx_stdlib(path: Path) -> tuple[list[dict], list[dict], list[str]]:
    blocks: list[dict] = []
    manual: list[dict] = []
    warnings: list[str] = []

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "word/document.xml" not in names:
            raise ValueError("not a Word document: word/document.xml is missing")
        relevant_xml = [
            name
            for name in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")
            if name in names
        ]
        expanded_xml_bytes = sum(archive.getinfo(name).file_size for name in relevant_xml)
        if expanded_xml_bytes > MAX_DOCX_XML_BYTES:
            raise ValueError("Word document XML exceeds the 100 MiB processing limit")
        root = ET.fromstring(archive.read("word/document.xml"))
        notes = read_note_parts(archive, names)
        if "word/comments.xml" in names:
            warnings.append("文档含批注，已忽略（批注不属于正文）")

    body = root.find(q("body"))
    if body is None:
        return blocks, _normalize_manual_review(manual), warnings

    index = 0
    for node in body:
        index += 1
        if node.tag == q("tbl"):
            rows = len(node.findall(q("tr")))
            cols = len(node.find(q("tr")).findall(q("tc"))) if rows else 0
            manual.append({
                "type": "table",
                "index": index,
                "message": f"表格需人工转换为 LaTeX tabular（约 {rows}×{cols}）；请勿自动生成",
            })
            continue

        if node.tag != q("p"):
            continue

        text, has_equation, has_image, note_references = paragraph_text(node)
        if has_equation:
            manual.append({"type": "equation", "index": index, "message": "公式为 OMML，需人工转写为 LaTeX 数学式"})
        if has_image:
            manual.append({"type": "image", "index": index, "message": "图片为嵌入资源，需人工导出并撰写 caption"})
        for kind, note_id in note_references:
            manual.append({
                "type": kind,
                "index": index,
                "label": note_id,
                "text": notes.get((kind, note_id), ""),
                "message": "脚注/尾注需人工转写并核对引用位置；请勿自动写入 LaTeX 正文",
            })
        if not text.strip():
            continue

        style_node = node.find(f".//{q('pStyle')}")
        level = heading_level_from_style(style_node.get(q("val"), "")) if style_node is not None else None
        if level is None and node.find(f".//{q('numPr')}") is not None:
            blocks.append({"type": "list_item", "text": text.strip(), "index": index})
        elif level is None:
            blocks.append({"type": "paragraph", "text": text.strip(), "index": index})
        else:
            blocks.append({"type": "heading", "level": level, "text": text.strip(), "index": index})

    return blocks, _normalize_manual_review(manual), warnings


def unescape_pandoc_markdown(text: str) -> str:
    r"""Compatibility hook that now preserves Pandoc Markdown verbatim.

    Earlier versions globally removed Markdown escapes, including ``\$`` and
    ``\|``.  That corrupted prices and table cells.  Citation brackets are
    unescaped only in a temporary scanner string in :func:`main`.
    """
    return text


def parse_docx_pandoc_analysis(path: Path, pandoc: str) -> dict:
    """Run Pandoc once and retain Word-origin safety semantics."""
    try:
        source = path.resolve()
        completed = run_captured(
            # Disabling the other table flavours forces pipe tables, which are
            # recognisable, but they still remain Word objects for review.
            [
                pandoc,
                "-t",
                "markdown-simple_tables-multiline_tables-grid_tables",
                "--wrap=none",
                "--",
                str(source),
            ],
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"pandoc timed out after {exc.timeout}s") from exc
    except OSError as exc:
        raise RuntimeError(f"unable to run pandoc: {exc}") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"pandoc failed: {completed.stderr.strip()[:400]}")
    return analyze_markdown(unescape_pandoc_markdown(completed.stdout), source_kind="pandoc-docx")


def parse_docx_pandoc(path: Path, pandoc: str) -> tuple[list[dict], list[dict], list[str]]:
    """Compatibility API returning the original three-list tuple."""
    analysis = parse_docx_pandoc_analysis(path, pandoc)
    return analysis["blocks"], analysis["manual_review"], []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument(
        "--force-stdlib",
        action="store_true",
        help="Skip Pandoc and use the standard-library .docx reader (for testing the fallback).",
    )
    args = parser.parse_args()

    path = Path(args.source)
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"source not found: {path}"}, ensure_ascii=False, indent=2))
        return 2
    if not path.is_file():
        print(json.dumps({"ok": False, "error": f"source is not a regular file: {path}"}, ensure_ascii=False, indent=2))
        return 2
    try:
        source_size = path.stat().st_size
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    if source_size > MAX_SOURCE_BYTES:
        print(json.dumps({
            "ok": False,
            "error": "source exceeds the 100 MiB processing limit",
            "source_bytes": source_size,
        }, ensure_ascii=False, indent=2))
        return 2

    suffix = path.suffix.lower()
    pandoc = None if args.force_stdlib else find_pandoc()
    warnings: list[str] = []
    detected_math = {
        "inline_count": 0,
        "display_count": 0,
        "total_count": 0,
        "spans": [],
        "unclosed": [],
    }
    conversion_candidates: list[dict] = []
    review_advisories: list[dict] = []

    try:
        if suffix == ".docx":
            fmt = "docx"
            if pandoc:
                analysis = parse_docx_pandoc_analysis(path, pandoc)
                blocks = analysis["blocks"]
                manual = analysis["manual_review"]
                detected_math = analysis["detected_math"]
                conversion_candidates = analysis["conversion_candidates"]
                review_advisories = analysis["review_advisories"]
                extractor = "pandoc"
            else:
                blocks, manual, warnings = parse_docx_stdlib(path)
                extractor = "stdlib-docx"
                if args.force_stdlib:
                    warnings.append(
                        "已按 --force-stdlib 使用标准库解析：复杂列表、脚注、样式保真度较低。"
                    )
                else:
                    warnings.append(
                        "未找到 pandoc，已使用标准库降级解析：复杂列表、脚注、样式保真度较低。"
                        "安装 pandoc 可提高保真度（macOS: brew install pandoc）。"
                    )
        elif suffix in {".md", ".markdown", ".txt"}:
            fmt = "markdown" if suffix != ".txt" else "text"
            analysis = analyze_markdown(path.read_text(encoding="utf-8"))
            blocks = analysis["blocks"]
            manual = analysis["manual_review"]
            detected_math = analysis["detected_math"]
            conversion_candidates = analysis["conversion_candidates"]
            review_advisories = analysis["review_advisories"]
            extractor = "markdown"
        else:
            print(json.dumps({
                "ok": False,
                "error": f"unsupported source format: {suffix or path.name}",
                "supported": [".docx", ".md", ".markdown", ".txt"],
            }, ensure_ascii=False, indent=2))
            return 2
    except (ValueError, RuntimeError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    except UnicodeDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"not valid UTF-8: {exc}"}, ensure_ascii=False, indent=2))
        return 1
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    body_text = "\n".join(block.get("text", "") for block in blocks)
    citation_scan_text = (
        re.sub(r"\\([\[\]])", r"\1", body_text)
        if extractor == "pandoc"
        else body_text
    )
    markers = sorted(set(collect_numeric_markers(citation_scan_text)))
    headings = [b for b in blocks if b["type"] == "heading"]

    result = {
        "ok": True,
        "schema_version": 2,
        "source": str(path),
        "format": fmt,
        "extractor": extractor,
        "pandoc_available": bool(find_pandoc()),
        "heading_count": len(headings),
        "block_count": len(blocks),
        "headings": headings,
        "blocks": blocks,
        "numeric_citation_markers": markers,
        "manual_review": _normalize_manual_review(manual),
        "detected_math": detected_math,
        "conversion_candidates": conversion_candidates,
        "review_advisories": review_advisories,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
