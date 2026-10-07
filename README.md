# RepoLens

Find out what is taking up space in a project before uploading or packaging it. RepoLens provides an **offline working-folder inventory**, the largest files, totals by extension, optional text-line counts and size budgets for CI.

Version **0.1.0** · Python **3.11+** · MIT · standard library only

[Download](https://github.com/MrTommyyyy/RepoLens/releases/latest) · [Report an issue](https://github.com/MrTommyyyy/RepoLens/issues)

![Tests](https://github.com/MrTommyyyy/RepoLens/actions/workflows/tests.yml/badge.svg)

## Why this exists

Large generated folders and accidental exports can hide the files that matter. I want a quick way to understand a project's contents and keep packaging surprises out of a release, without running the project or installing its dependencies.

## Use it

```sh
python repolens.py /path/to/project
python repolens.py . --top 20 --lines --exclude "assets/*"
python repolens.py . --max-file-mb 10 --max-total-mb 100 --json
python repolens.py . --output inventory.json
```

Paths in the report are relative to the selected folder. Largest-file ties are ordered by filename, so output stays predictable. Use `python3` where your system requires it.

For a disposable sample project:

```sh
python demo.py
```

The demo creates a source file, a generated folder and an oversized asset in a temporary directory, checks a size budget, then removes its own temporary directory.

## Windows executable

Extract `RepoLens-0.1.0-Windows-x64.zip` and run from PowerShell:

```powershell
.\RepoLens.exe "C:\projects\my-app" --lines --max-file-mb 10
```

Python is bundled. This is a **terminal application**. The source ZIP supports Python 3.11+ on Windows, macOS and Linux.

## Included information

| Report section | Meaning |
| --- | --- |
| File count and total bytes | Included regular files in the working folder |
| Largest files | Up to `--top` results; default 10 |
| Extensions | File count and bytes by lowercase suffix |
| Optional text lines | Physical newline-based counts; includes comments and blank lines |
| Skipped folders and links | Explains what was excluded |
| Budgets | Files over the per-file limit and whether the included total exceeds its limit |
| Inspection issues | Inaccessible or changing files; the result fails rather than silently passing |

## Exclusions and line counts

Generated directory names skipped at every depth: `.git`, `node_modules`, `.venv`, `venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.next`, `dist`, `build` and `target`. Other hidden files are included.

Repeat `--exclude GLOB` for case-sensitive patterns against relative paths, for example `--exclude "*.log" --exclude "private"`. Patterns use Python `fnmatch`; `*` can match across `/`. Matching a directory prevents traversal. Symbolic-link files and directories are skipped.

**Git ignore rules, tracked status, language detection and Git history are not evaluated.** Extension totals do not establish the programming language. Hard-linked files count once for each path; reported sizes are logical file sizes, not physical disk usage. The default exclusions cannot currently be disabled.

`--lines` reads UTF-8 files up to 2 MiB and skips NUL-containing binary files, unsupported encodings and larger files. Skipped files remain in byte totals. A final line without a newline counts once. These are text lines, not executable code-line metrics. Inventory is a best-effort view of an idle folder, not a locked filesystem snapshot.

## Budgets and reports

`--max-file-mb` and `--max-total-mb` use MiB (1,048,576 bytes). A file exactly at a limit passes. With no configured budgets, size alone does not fail the check.

- Exit `0`: inventory finished without inspection issues or exceeded budgets.
- Exit `1`: inspection issues or a configured budget was exceeded.
- Exit `2`: invalid input, missing folder or export failure.

`--output` saves a complete report to a **new `.json` file**. Existing files and symbolic links are refused. Choose a new filename for another run; this prevents a report export from replacing a source file. The chosen output is omitted from that run's inventory. Saving requires a filesystem that supports hard links, including normal NTFS and Unix filesystems.

Reports contain project filenames and the selected folder path; review them before posting publicly. File contents are never printed. Default scans use filesystem metadata; `--lines` reads text for counting. The tool does not execute project code, follow links, make network requests or delete project files.

## Development and CI

```sh
python -m unittest discover -s tests -v
python repolens.py . --max-file-mb 5 --max-total-mb 25
```

Nine tests cover deterministic totals, exclusions, links, line-count limits, exact budget boundaries, protected exports and actual CLI behaviour. CI runs on Windows, macOS and Linux; Windows builds also test the packaged executable on disposable inputs.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md). Licensed under [MIT](LICENSE).
