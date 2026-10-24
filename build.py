"""Build script to generate standalone SyncTone.exe using PyInstaller."""

import os
import subprocess
import sys
from pathlib import Path


def kill_existing_processes():
    """Terminate any running SyncTone.exe instances to avoid file lock on Windows."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "SyncTone.exe"],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass


def build():
    root_dir = Path(__file__).resolve().parent
    spec_file = root_dir / "SyncTone.spec"
    exe_path = root_dir / "dist" / "SyncTone.exe"

    kill_existing_processes()

    # If the file still exists, verify it can be written to
    if exe_path.exists():
        try:
            exe_path.unlink()
        except PermissionError:
            print(f"[ERROR] Cannot overwrite {exe_path}. Ensure it is not running and try again.")
            sys.exit(1)

    print("Building SyncTone.exe...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "-y",
        str(spec_file),
    ]

    result = subprocess.run(cmd, cwd=root_dir)
    if result.returncode == 0:
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n[SUCCESS] Build completed successfully!")
            print(f"Output: {exe_path} ({size_mb:.1f} MB)\n")
        else:
            print("\n[SUCCESS] Build finished successfully.\n")
    else:
        print(f"\n[ERROR] Build failed with exit code {result.returncode}\n")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
