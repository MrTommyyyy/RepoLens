"""Check the packaged CLI using a disposable synthetic project."""
import json
from pathlib import Path
import subprocess
import tempfile

EXE = Path("dist/RepoLens.exe").resolve()
def run(*args, code=0):
    result = subprocess.run([str(EXE), *map(str, args)], capture_output=True, text=True, timeout=60)
    assert result.returncode == code, (result.returncode, result.stdout, result.stderr)
    return result.stdout

assert run("--version").strip() == "0.1.0"
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    (folder / "main.py").write_text("print('synthetic')\n")
    (folder / "node_modules").mkdir()
    (folder / "node_modules" / "ignored.txt").write_text("ignored")
    report = json.loads(run(folder, "--json", "--lines"))
    assert report["files"] == 1 and report["line_statistics"]["total_lines"] == 1
    run(folder, "--max-file-mb", "0", code=1)
    output = folder / "inventory.json"
    run(folder, "--output", output)
    before = output.read_bytes()
    run(folder, "--output", output, code=2)
    assert output.read_bytes() == before
    run(folder / "missing", code=2)
print("Packaged RepoLens inventory, budgets and export checks passed")
