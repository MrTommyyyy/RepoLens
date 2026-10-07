"""Offline repository inventory and size budgets, without executing project code."""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import fnmatch
import json
import os
from pathlib import Path
import stat
import tempfile

VERSION = "0.1.0"
DEFAULT_EXCLUDES = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".next", "dist", "build", "target"})
LINE_LIMIT = 2 * 1024 * 1024


def _excluded(relative: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(relative + "/", pattern) for pattern in patterns)


def inventory(folder: str | Path, *, top: int = 10, excludes=(), lines: bool = False,
              max_file_bytes: int | None = None, max_total_bytes: int | None = None, omit=()) -> dict:
    root = Path(folder)
    if not root.is_dir():
        raise ValueError("Choose an existing project folder.")
    if not 1 <= top <= 1000:
        raise ValueError("Top file count must be between 1 and 1000.")
    for limit in (max_file_bytes, max_total_bytes):
        if limit is not None and limit < 0:
            raise ValueError("Size budgets cannot be negative.")
    omitted = {Path(path).resolve() for path in omit}
    files, issues, skipped_links, skipped_dirs = [], [], [], []
    extensions = defaultdict(lambda: {"files": 0, "bytes": 0, "lines": 0})
    line_stats = {"enabled": lines, "files_counted": 0, "files_skipped": 0, "total_lines": 0}
    def walk_error(error):
        issues.append({"path": str(Path(error.filename).relative_to(root)) if error.filename else ".", "detail": "Could not list folder."})
    for parent, directories, names in os.walk(root, followlinks=False, onerror=walk_error):
        parent = Path(parent)
        kept = []
        for name in sorted(directories):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                skipped_links.append(relative)
            elif name in DEFAULT_EXCLUDES or _excluded(relative, excludes):
                skipped_dirs.append(relative)
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if _excluded(relative, excludes):
                continue
            if path.is_symlink():
                skipped_links.append(relative)
                continue
            if path.resolve() in omitted:
                continue
            try:
                before = path.stat()
                if not stat.S_ISREG(before.st_mode):
                    continue
                entry = {"path": relative, "bytes": before.st_size}
                extension = path.suffix.lower() or "[no extension]"
                bucket = extensions[extension]
                if lines:
                    count = None
                    if before.st_size <= LINE_LIMIT:
                        with path.open("rb") as stream:
                            data = stream.read(LINE_LIMIT + 1)
                        if len(data) <= LINE_LIMIT and b"\x00" not in data:
                            try:
                                text = data.decode("utf-8-sig")
                                count = text.count("\n") + int(bool(text) and not text.endswith("\n"))
                            except UnicodeDecodeError:
                                pass
                        after = path.stat()
                        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                            issues.append({"path": relative, "detail": "File changed while counting lines."})
                            count = None
                    if count is None:
                        line_stats["files_skipped"] += 1
                    else:
                        entry["lines"] = count
                        line_stats["files_counted"] += 1
                        line_stats["total_lines"] += count
                        bucket["lines"] += count
                files.append(entry)
                bucket["files"] += 1
                bucket["bytes"] += before.st_size
            except OSError:
                issues.append({"path": relative, "detail": "Could not inspect file."})
    total = sum(item["bytes"] for item in files)
    largest = sorted(files, key=lambda item: (-item["bytes"], item["path"]))[:top]
    oversized = sorted((item for item in files if max_file_bytes is not None and item["bytes"] > max_file_bytes), key=lambda item: item["path"])
    total_exceeded = max_total_bytes is not None and total > max_total_bytes
    return {"format": "repolens/v1", "version": VERSION, "folder": str(root), "files": len(files), "bytes": total,
            "largest_files": largest, "extensions": dict(sorted(extensions.items())), "line_statistics": line_stats,
            "excluded_directories": sorted(skipped_dirs), "skipped_symlinks": sorted(skipped_links), "issues": issues,
            "budgets": {"max_file_bytes": max_file_bytes, "max_total_bytes": max_total_bytes,
                        "oversized_files": oversized, "total_exceeded": total_exceeded},
            "ok": not (issues or oversized or total_exceeded)}


def human_size(size: int) -> str:
    return f"{size / (1024 * 1024):.2f} MiB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KiB"


def summary(report: dict) -> str:
    lines = [f"RepoLens — {report['files']} files, {human_size(report['bytes'])}", "Largest included files:"]
    lines.extend(f"  {human_size(item['bytes']):>12}  {item['path']}" for item in report["largest_files"])
    if report["line_statistics"]["enabled"]:
        counts = report["line_statistics"]
        lines.append(f"Text lines: {counts['total_lines']} across {counts['files_counted']} files ({counts['files_skipped']} skipped)")
    lines.append(f"Skipped {len(report['excluded_directories'])} generated folders and {len(report['skipped_symlinks'])} symbolic links.")
    for item in report["budgets"]["oversized_files"]:
        lines.append("Over file budget: " + item["path"])
    if report["budgets"]["total_exceeded"]:
        lines.append("Included total exceeds the configured budget.")
    lines.extend(f"Issue: {item['path']} — {item['detail']}" for item in report["issues"])
    lines.append("Working-folder inventory; .gitignore rules and Git history are not evaluated.")
    return "\n".join(lines)


def save_report(report: dict, output: str | Path) -> None:
    """Publish complete JSON to a new path only; existing files are never replaced."""
    output = Path(output)
    if output.suffix.lower() != ".json" or output.is_symlink():
        raise ValueError("Choose a new .json output that is not a symbolic link.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, prefix=".repolens-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def mib(text: str) -> int:
    try:
        value = Decimal(text)
        if not value.is_finite() or value < 0:
            raise ValueError()
        return int(value * 1024 * 1024)
    except (ValueError, InvalidOperation, OverflowError):
        raise argparse.ArgumentTypeError("Use a non-negative finite size in MiB.") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--top", type=int, default=10, help="Show 1–1000 largest included files")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="Repeatable case-sensitive relative-path glob")
    parser.add_argument("--lines", action="store_true", help="Count physical lines in UTF-8 files up to 2 MiB")
    parser.add_argument("--max-file-mb", type=mib, help="Fail if any included file exceeds this MiB budget")
    parser.add_argument("--max-total-mb", type=mib, help="Fail if included files exceed this total MiB budget")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, help="Save to a new .json file; existing files are refused")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    try:
        report = inventory(args.folder, top=args.top, excludes=args.exclude, lines=args.lines,
                           max_file_bytes=args.max_file_mb, max_total_bytes=args.max_total_mb,
                           omit=[args.output] if args.output else [])
        if args.output:
            save_report(report, args.output)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2) if args.json else summary(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
