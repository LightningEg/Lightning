"""Install the source launcher's dependencies from their existing authoritative inputs."""
from pathlib import Path
import subprocess
import sys
import tomllib


def main():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text())
    encrypted = metadata["project"]["optional-dependencies"]["encrypted"]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                           "--disable-pip-version-check", "-r", str(root / "requirements.txt"), *encrypted])


if __name__ == "__main__":
    main()
