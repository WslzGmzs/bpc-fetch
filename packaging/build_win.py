"""Build script for Windows exe distribution."""
import subprocess
import sys
from pathlib import Path


def build():
    spec = Path(__file__).parent / "bpc-fetch.spec"
    if not spec.exists():
        print(f"ERROR: {spec} not found")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec),
    ]
    print(f"Running: {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=spec.parent.parent)
    if r.returncode == 0:
        print("\nBuild complete: dist/bpc-fetch.exe")
        print("First run: bpc-fetch.exe install-browser")
    else:
        print("\nBuild failed")
        sys.exit(r.returncode)


if __name__ == "__main__":
    build()
