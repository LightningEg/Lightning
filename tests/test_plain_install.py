"""The demo/sample backend remains importable without encrypted extras."""
import subprocess
import sys
from pathlib import Path

BLOCK = """
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.split('.')[0] in ('cryptography', 'sqlcipher3'):
            raise ModuleNotFoundError(name)
sys.meta_path.insert(0, Block())
from lightning.ui.web import create_app
from lightning.bootstrap import build
create_app(build(sys.argv[1], backup_on_start=False))
"""


def test_plain_app_starts_without_encrypted_extras(tmp_path):
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, "-c", BLOCK, str(tmp_path / "plain.db")], cwd=root,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
