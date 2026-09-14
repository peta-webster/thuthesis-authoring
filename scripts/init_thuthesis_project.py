#!/usr/bin/env python3
"""Create a new project from an official ThuThesis release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

from _thuthesis_paths import is_safe_target


GITHUB_RELEASE_URL = (
    "https://github.com/tuna/thuthesis/releases/download/"
    "v{version}/thuthesis-v{version}.zip"
)
VERSION_RE = re.compile(r"^v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
REQUIRED_FILES = {
    "LICENSE",
    "thuthesis.cls",
    "thuthesis-example.tex",
    "thuthesis-example.pdf",
    "thuthesis.pdf",
    "thusetup.tex",
    "ref/refs.bib",
}
DEFAULT_USER_MAIN = "main.tex"
MAIN_INPUT_RE = re.compile(r"(?m)^[ \t]*\\(?:input|include)\{[^}]+\}[^\n]*(?:\n|$)")
ROOT_DIRECTIVE_RE = re.compile(
    r"(?im)^(?P<prefix>%\s*!TEX\s+root\s*=\s*)(?:\.\.?/)*thuthesis-example\.tex(?P<suffix>\s*)$"
)
THUSETUP_INPUT_RE = re.compile(
    r"(?m)^[ \t]*\\input\{thusetup\}[ \t]*(?:%[^\n]*)?(?:\n|$)"
)
METADATA_OVERLAY_BEGIN = "% thuthesis-authoring: begin user metadata overlay"
METADATA_OVERLAY_END = "% thuthesis-authoring: end user metadata overlay"
METADATA_TODO_FIELDS = (
    "title",
    "title*",
    "degree-category",
    "degree-category*",
    "department",
    "discipline",
    "discipline*",
    "author",
    "author*",
    "supervisor",
    "supervisor*",
)
CLEARED_TEMPLATE_FIELDS = ("associate-supervisor", "associate-supervisor*")
METADATA_OVERLAY = r"""% thuthesis-authoring: begin user metadata overlay
\thusetup{
  title                 = {[TODO: 中文论文题目]},
  title*                = {[TODO: English Thesis Title]},
  degree-category       = {[TODO: 学位类别]},
  degree-category*      = {[TODO: Degree Category]},
  department            = {[TODO: 培养单位]},
  discipline            = {[TODO: 学科名称]},
  discipline*           = {[TODO: Discipline]},
  author                = {[TODO: 作者姓名]},
  author*               = {[TODO: Author Name]},
  supervisor            = {[TODO: 指导教师]},
  supervisor*           = {[TODO: Supervisor]},
  associate-supervisor  = {},
  associate-supervisor* = {},
}
% thuthesis-authoring: end user metadata overlay
"""
ORDINARY_PAGE_NOTICE = (
    "[TODO: 本页仍为 ThuThesis 官方模板示例内容；"
    "请根据实际材料替换，若不需要请从用户 main 中移除。]"
)
BLOCKING_PAGE_NOTICE = (
    "[TODO: BLOCKING: 本页仍为 ThuThesis 官方模板示例内容，包含敏感或流程性信息；"
    "禁止直接提交。请替换为真实材料，或从用户 main 中移除。]"
)
PAGE_ANNOTATIONS = {
    "data/denotation.tex": ("denotation", False),
    "data/appendix.tex": ("chapter", False),
    "data/acknowledgements.tex": ("acknowledgements", False),
    "data/committee.tex": ("committee", True),
    "data/resume.tex": ("resume", True),
    "data/comments.tex": ("comments", True),
    "data/resolution.tex": ("resolution", True),
}


class InitializationError(RuntimeError):
    """A safe, user-facing initialization failure."""


def normalize_version(raw: str) -> str:
    match = VERSION_RE.fullmatch(raw.strip())
    if not match:
        raise InitializationError("version must look like 7.7.1 or v7.7.1")
    return match.group(1)


def release_url(version: str) -> str:
    return GITHUB_RELEASE_URL.format(version=version)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(expected: Optional[str], actual: str) -> None:
    if expected and actual != expected:
        raise InitializationError(f"SHA-256 mismatch: expected {expected}, got {actual}")


def validate_download_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    final_host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https":
        raise InitializationError("official release download must remain on HTTPS after redirects")
    if final_host != "github.com" and not final_host.endswith(".githubusercontent.com"):
        raise InitializationError(f"official release redirected to an unexpected host: {final_host or 'unknown'}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise InitializationError("official release URL contains an invalid port") from exc
    if port not in {None, 443}:
        raise InitializationError(f"official release redirected to an unexpected HTTPS port: {port}")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject an unsafe redirect before urllib connects to its target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        validate_download_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def download_release(version: str, output: Path, timeout: int) -> tuple[str, str]:
    url = release_url(version)
    validate_download_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "thuthesis-authoring"})
    opener = urllib.request.build_opener(SafeRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response, output.open("wb") as stream:
            validate_download_url(response.geturl())
            announced = response.headers.get("Content-Length")
            if announced and int(announced) > MAX_DOWNLOAD_BYTES:
                raise InitializationError("release archive exceeds the 100 MiB download limit")
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise InitializationError("release archive exceeds the 100 MiB download limit")
                stream.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise InitializationError(f"unable to download official release: {exc}") from exc
    return url, sha256_file(output)


def safe_member_path(member: zipfile.ZipInfo) -> PurePosixPath:
    raw = member.filename.replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or raw.startswith("/") or any(part in {"", ".", ".."} for part in path.parts):
        raise InitializationError(f"unsafe archive member: {member.filename!r}")
    if member.flag_bits & 0x1:
        raise InitializationError(f"encrypted archive member is not supported: {member.filename!r}")
    unix_mode = (member.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise InitializationError(f"non-regular archive member is not supported: {member.filename!r}")
    return path


def extract_zip_safely(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise InitializationError("release archive contains too many files")
            total_size = 0
            seen: set[str] = set()
            for member in members:
                relative = safe_member_path(member)
                normalized = relative.as_posix().rstrip("/")
                comparison_key = unicodedata.normalize("NFC", normalized).casefold()
                if comparison_key in seen:
                    raise InitializationError(f"duplicate archive member: {member.filename!r}")
                seen.add(comparison_key)
                total_size += member.file_size
                if total_size > MAX_EXTRACTED_BYTES:
                    raise InitializationError("release archive exceeds the 256 MiB extraction limit")
                target = destination.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except (zipfile.BadZipFile, OSError) as exc:
        raise InitializationError(f"unable to extract release archive: {exc}") from exc


def validate_release_tree(root: Path) -> None:
    """Bound and type-check a local or extracted release tree without following links."""

    member_count = 0
    total_size = 0
    seen: set[str] = set()
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = directory.iterdir()
        except OSError as exc:
            raise InitializationError(f"unable to inspect release source: {exc}") from exc
        try:
            for path in entries:
                relative = path.relative_to(root).as_posix()
                comparison_key = unicodedata.normalize("NFC", relative).casefold()
                if comparison_key in seen:
                    raise InitializationError(f"release source contains a case-insensitive duplicate path: {relative}")
                seen.add(comparison_key)
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    raise InitializationError("release source contains too many files")
                if path.is_symlink():
                    raise InitializationError(f"source contains unsupported symbolic link: {relative}")
                stat_result = path.stat()
                if path.is_dir():
                    stack.append(path)
                elif path.is_file():
                    total_size += stat_result.st_size
                    if total_size > MAX_EXTRACTED_BYTES:
                        raise InitializationError("release source exceeds the 256 MiB size limit")
                else:
                    raise InitializationError(f"source contains a non-regular member: {relative}")
        except OSError as exc:
            raise InitializationError(f"unable to inspect release source member: {exc}") from exc


def validate_release_root(root: Path) -> list[str]:
    validate_release_tree(root)
    missing = sorted(path for path in REQUIRED_FILES if not (root / path).is_file())
    if not (root / "data").is_dir():
        missing.append("data/")
    if missing:
        raise InitializationError("source is not a complete official ThuThesis release; missing: " + ", ".join(missing))
    main_text = (root / "thuthesis-example.tex").read_text(encoding="utf-8", errors="replace")
    if not re.search(r"\\documentclass(?:\[[^\]]*\])?\{thuthesis\}", main_text):
        raise InitializationError("thuthesis-example.tex does not use the thuthesis document class")
    return sorted(path.relative_to(root).as_posix() for path in (root / "data").glob("*.tex"))


def normalize_user_main(raw: str) -> str:
    path = PurePosixPath(raw.replace("\\", "/"))
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or path.suffix.lower() != ".tex"
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.tex", path.name)
        or path.name.startswith("-")
        or path.name.lower() == "thuthesis-example.tex"
    ):
        raise InitializationError(
            "--main must be a conservative root-level .tex filename other than thuthesis-example.tex"
        )
    return path.as_posix()


def normalize_chapters(raw_chapters: list[str]) -> list[str]:
    chapters: list[str] = []
    seen: set[str] = set()
    for raw in raw_chapters:
        path = PurePosixPath(raw.replace("\\", "/"))
        relative = Path(path.as_posix())
        if path.is_absolute() or not is_safe_target(relative):
            raise InitializationError("--chapter must be a non-sensitive data/*.tex path")
        normalized = path.as_posix()
        if normalized in seen:
            raise InitializationError(f"duplicate --chapter path: {normalized}")
        seen.add(normalized)
        chapters.append(normalized)
    return chapters


def natural_key(value: str) -> list[tuple[int, object]]:
    return [
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    ]


def discover_chapters(root: Path) -> list[str]:
    chapters = [
        path.relative_to(root).as_posix()
        for path in (root / "data").glob("chap*.tex")
        if path.is_file() and not path.is_symlink()
    ]
    return sorted(chapters, key=natural_key)


def assemble_main_text(example_text: str, chapters: list[str]) -> str:
    mainmatter = re.search(r"(?m)^\\mainmatter\b[^\n]*(?:\n|$)", example_text)
    if not mainmatter:
        raise InitializationError("official example has no \\mainmatter assembly point")
    tail = example_text[mainmatter.end():]
    boundary = re.search(
        r"(?m)^[ \t]*(?:\\bibliography\{|\\printbibliography\b|\\appendix\b|\\backmatter\b)",
        tail,
    )
    if not boundary:
        raise InitializationError("official example has no bibliography or back-matter boundary")
    body_start = mainmatter.end()
    body = example_text[body_start:body_start + boundary.start()]
    inputs = list(MAIN_INPUT_RE.finditer(body))
    if not inputs:
        raise InitializationError("official example has no replaceable main-matter inputs")
    replacement = "".join(
        f"\\input{{{Path(chapter).with_suffix('').as_posix()}}}\n"
        for chapter in chapters
    )
    return (
        example_text[:body_start + inputs[0].start()]
        + replacement
        + example_text[body_start + inputs[-1].end():]
    )


def add_metadata_overlay(main_text: str) -> str:
    """Insert one user-owned metadata override after the active setup input."""

    if METADATA_OVERLAY_BEGIN in main_text or METADATA_OVERLAY_END in main_text:
        raise InitializationError("official example unexpectedly contains a generated metadata overlay marker")
    matches = list(THUSETUP_INPUT_RE.finditer(main_text))
    if len(matches) != 1:
        raise InitializationError(
            "official example must contain exactly one active \\input{thusetup} assembly point"
        )
    match = matches[0]
    separator = "" if main_text[:match.end()].endswith("\n") else "\n"
    return main_text[:match.end()] + separator + METADATA_OVERLAY + main_text[match.end():]


def page_anchor_pattern(anchor: str) -> re.Pattern[str]:
    if anchor == "chapter":
        return re.compile(r"(?m)^[ \t]*\\chapter\{[^}\n]+\}[ \t]*(?:%[^\n]*)?(?:\n|$)")
    escaped = re.escape(anchor)
    return re.compile(
        rf"(?m)^[ \t]*\\begin\{{{escaped}\}}(?:\[[^\n]*\])?[ \t]*(?:%[^\n]*)?(?:\n|$)"
    )


def page_notice(anchor: str, blocking: bool) -> str:
    message = BLOCKING_PAGE_NOTICE if blocking else ORDINARY_PAGE_NOTICE
    emphasis = r"\bfseries " if blocking else ""
    item_prefix = "  \\item[]\n" if anchor == "denotation" else ""
    return (
        "\n" + item_prefix + "\\begin{center}\n"
        f"  \\fbox{{\\parbox{{0.9\\linewidth}}{{{emphasis}{message}}}}}\n"
        "\\end{center}\n\n"
    )


def annotate_example_page(text: str, anchor: str, blocking: bool, relative: str) -> str:
    """Insert one visible warning after an unambiguous active page heading."""

    if ORDINARY_PAGE_NOTICE in text or BLOCKING_PAGE_NOTICE in text:
        raise InitializationError(f"official page unexpectedly contains a generated notice: {relative}")
    matches = list(page_anchor_pattern(anchor).finditer(text))
    if len(matches) != 1:
        raise InitializationError(
            f"official page must contain exactly one active {anchor!r} annotation point: {relative}"
        )
    match = matches[0]
    return text[:match.end()] + page_notice(anchor, blocking) + text[match.end():]


def annotate_example_pages(root: Path) -> tuple[list[str], list[str]]:
    ordinary: list[str] = []
    sensitive: list[str] = []
    for relative, (anchor, blocking) in PAGE_ANNOTATIONS.items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise InitializationError(f"official example page is missing or not a regular file: {relative}")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            raise InitializationError(f"unable to read official example page: {relative}: {exc}") from exc
        annotated = annotate_example_page(text, anchor, blocking, relative)
        path.write_text(annotated, encoding="utf-8")
        (sensitive if blocking else ordinary).append(relative)
    return ordinary, sensitive


def update_root_directives(
    root: Path,
    main_path: Path,
    chapters: list[str],
) -> list[str]:
    updated: list[str] = []
    for chapter in chapters:
        path = root / chapter
        text = path.read_text(encoding="utf-8")
        relative_main = os.path.relpath(main_path, path.parent).replace(os.sep, "/")
        if not relative_main.startswith("."):
            relative_main = "./" + relative_main
        replaced, count = ROOT_DIRECTIVE_RE.subn(
            lambda match: match.group("prefix") + relative_main + match.group("suffix"),
            text,
        )
        if not count and not re.search(r"(?im)^%\s*!TEX\s+root\s*=", text):
            replaced = f"% !TEX root = {relative_main}\n" + text
            count = 1
        if count:
            path.write_text(replaced, encoding="utf-8")
            updated.append(path.relative_to(root).as_posix())
    return updated


def locate_release_root(extracted: Path) -> tuple[Path, list[str]]:
    candidates = [extracted] + sorted(path for path in extracted.iterdir() if path.is_dir())
    valid: list[tuple[Path, list[str]]] = []
    for candidate in candidates:
        try:
            data_files = validate_release_root(candidate)
        except InitializationError:
            continue
        valid.append((candidate, data_files))
    if len(valid) != 1:
        raise InitializationError(f"archive must contain exactly one official ThuThesis release root; found {len(valid)}")
    return valid[0]


def copy_release(
    source: Path,
    destination: Path,
    user_main: str = DEFAULT_USER_MAIN,
    chapters: Optional[list[str]] = None,
) -> dict[str, object]:
    user_main = normalize_user_main(user_main)
    chapters = normalize_chapters(chapters) if chapters is not None else None
    if destination.exists() or destination.is_symlink():
        raise InitializationError(
            f"destination already exists or is a symbolic link; refusing to overwrite: {destination}"
        )
    source = source.resolve()
    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise InitializationError("destination must not be inside the source release directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}.init-", dir=str(destination.parent)) as temp:
        staging = Path(temp) / "project"
        shutil.copytree(source, staging)
        validate_release_root(staging)
        example = staging / "thuthesis-example.tex"
        example_sha256 = sha256_file(example)
        selected_chapters = discover_chapters(staging) if chapters is None else chapters
        if not selected_chapters:
            raise InitializationError("no chapter files were selected for the user main")
        created_chapters: list[str] = []
        for chapter in selected_chapters:
            chapter_path = staging / chapter
            if chapter_path.exists() or chapter_path.is_symlink():
                if chapter_path.is_symlink() or not chapter_path.is_file():
                    raise InitializationError(f"selected chapter is not a regular file: {chapter}")
            else:
                try:
                    chapter_path.parent.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise InitializationError(
                        f"cannot create selected chapter path: {chapter}"
                    ) from exc
                chapter_path.write_text("", encoding="utf-8")
                created_chapters.append(chapter)
        main_path = staging / user_main
        if main_path.exists() or main_path.is_symlink():
            raise InitializationError(f"user main already exists in release source: {user_main}")
        shutil.copy2(example, main_path)
        main_text = assemble_main_text(main_path.read_text(encoding="utf-8"), selected_chapters)
        main_path.write_text(add_metadata_overlay(main_text), encoding="utf-8")
        annotated_optional_files, annotated_sensitive_files = annotate_example_pages(staging)
        root_directive_files = update_root_directives(staging, main_path, selected_chapters)
        if sha256_file(example) != example_sha256:
            raise InitializationError("official thuthesis-example.tex changed while creating the user main")
        staging.rename(destination)
    return {
        "main_file": user_main,
        "main_source": "thuthesis-example.tex",
        "chapter_files": selected_chapters,
        "created_chapter_files": created_chapters,
        "root_directive_files": root_directive_files,
        "example_sha256": example_sha256,
        "metadata_todo_fields": list(METADATA_TODO_FIELDS),
        "cleared_template_fields": list(CLEARED_TEMPLATE_FIELDS),
        "annotated_optional_files": annotated_optional_files,
        "annotated_sensitive_files": annotated_sensitive_files,
        "generated_todo_count": len(METADATA_TODO_FIELDS) + len(PAGE_ANNOTATIONS),
    }


def initialize(args: argparse.Namespace) -> dict[str, object]:
    requested_destination = Path(args.destination).expanduser()
    if not requested_destination.is_absolute():
        requested_destination = Path.cwd() / requested_destination
    if requested_destination.name in {"", ".", ".."}:
        raise InitializationError("destination must name a new project directory")
    destination = requested_destination.parent.resolve() / requested_destination.name
    if destination.exists() or destination.is_symlink():
        raise InitializationError(
            f"destination already exists or is a symbolic link; refusing to overwrite: {destination}"
        )
    if args.sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
        raise InitializationError("SHA-256 must contain exactly 64 hexadecimal characters")
    if args.timeout <= 0:
        raise InitializationError("timeout must be greater than zero")
    expected_sha256 = args.sha256.lower() if args.sha256 else None
    user_main = normalize_user_main(getattr(args, "main", DEFAULT_USER_MAIN))
    requested_chapters = getattr(args, "chapter", None)
    chapters = normalize_chapters(requested_chapters) if requested_chapters else None

    source_kind: str
    source_label: str
    version: Optional[str] = None
    archive_sha256: Optional[str] = None
    download_url: Optional[str] = None

    with tempfile.TemporaryDirectory(prefix="thuthesis-authoring-init-") as temp:
        temp_root = Path(temp)
        if args.version:
            version = normalize_version(args.version)
            archive = temp_root / f"thuthesis-v{version}.zip"
            download_url, archive_sha256 = download_release(version, archive, args.timeout)
            verify_sha256(expected_sha256, archive_sha256)
            source_kind = "official_download"
            source_label = download_url
            extracted = temp_root / "extracted"
            extracted.mkdir()
            extract_zip_safely(archive, extracted)
            source_root, data_files = locate_release_root(extracted)
        else:
            source = Path(args.source).expanduser().resolve()
            if not source.exists():
                raise InitializationError(f"source does not exist: {source}")
            source_label = str(source)
            if source.is_dir():
                if expected_sha256:
                    raise InitializationError("--sha256 applies only to downloaded or local .zip archives")
                source_kind = "local_directory"
                source_root = source
                data_files = validate_release_root(source_root)
            elif source.is_file() and source.suffix.lower() == ".zip":
                source_kind = "local_archive"
                archive_sha256 = sha256_file(source)
                verify_sha256(expected_sha256, archive_sha256)
                extracted = temp_root / "extracted"
                extracted.mkdir()
                extract_zip_safely(source, extracted)
                source_root, data_files = locate_release_root(extracted)
            else:
                raise InitializationError("local source must be an official release directory or .zip archive")

        main_result = copy_release(source_root, destination, user_main, chapters)

    result: dict[str, object] = {
        "ok": True,
        "destination": str(destination),
        "source_kind": source_kind,
        "source": source_label,
        "version": version,
        "archive_sha256": archive_sha256,
        "data_files": data_files,
        **main_result,
        "next_step": (
            "inspect the new project and report provenance; stop there for initialize-only requests, "
            "or validate explicitly selected authoring targets before any content edit"
        ),
    }
    if download_url:
        result["download_url"] = download_url
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a new project from an exact official ThuThesis release without overwriting existing files."
    )
    parser.add_argument("destination", help="new project directory; it must not already exist")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--version", help="official GitHub release version, for example 7.7.1")
    source_group.add_argument("--source", help="local official release directory or .zip archive")
    parser.add_argument("--sha256", help="optional expected SHA-256 for a downloaded or local archive")
    parser.add_argument(
        "--main",
        default=DEFAULT_USER_MAIN,
        help="new root-level user main copied from thuthesis-example.tex (default: main.tex)",
    )
    parser.add_argument(
        "--chapter",
        action="append",
        help=(
            "planned safe data/*.tex chapter to include, in mapping order; repeat as needed. "
            "Missing planned files are created empty for the authoring step. "
            "Without this option, existing data/chap*.tex files are discovered in natural order."
        ),
    )
    parser.add_argument("--timeout", type=int, default=60, help="download timeout in seconds (default: 60)")
    args = parser.parse_args()

    try:
        result = initialize(args)
    except InitializationError as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    except OSError as exc:
        print(json.dumps({"ok": False, "reason": f"filesystem operation failed: {exc}"}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
