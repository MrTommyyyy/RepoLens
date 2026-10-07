"""Inspect a synthetic project, leaving real projects untouched."""
from pathlib import Path
import tempfile
from repolens import inventory, summary

with tempfile.TemporaryDirectory(prefix="repolens-demo-") as directory:
    folder = Path(directory)
    (folder / "main.py").write_text("# synthetic example\nprint('hello')\n")
    (folder / "asset.bin").write_bytes(b"\x00" * 2048)
    generated = folder / "node_modules"
    generated.mkdir()
    (generated / "ignored.bin").write_bytes(b"x" * 4096)
    print(summary(inventory(folder, lines=True, max_file_bytes=1024)))
