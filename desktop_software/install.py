#!/usr/bin/env python3
"""
Cross-platform installer/uninstaller for mpy_tool wheels.
Features:
- Auto-detect version from wheel filename (optional --version)
- User vs system mode
- Multiple version support
- Linux/macOS wrapper scripts with CLI args forwarding
- Windows .bat launchers
- Automatic .desktop file creation on Linux
- install, uninstall, status commands
"""

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "mpy_tool"
COMMANDS = ["mpy_tool", "mpy_tool_gui"]  # commands to create launchers


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} installer")
    sub = parser.add_subparsers(dest="command", required=True)

    # Install
    p = sub.add_parser("install")
    p.add_argument("wheel", help="Path to the Python wheel (.whl)")
    p.add_argument("--version", help="Version being installed (auto-detected if omitted)", default=None)
    p.add_argument("--base", help="Installation base path", default=str(Path.home() / f".{APP_NAME}"))
    p.add_argument("--mode", choices=["user", "system"], default="user")

    # Uninstall
    p = sub.add_parser("uninstall")
    p.add_argument("--all", action="store_true", help="Remove all versions")
    p.add_argument("--version", help="Specific version to remove")
    p.add_argument("--base", help="Installation base path", default=str(Path.home() / f".{APP_NAME}"))
    p.add_argument("--mode", choices=["user", "system"], default="user")

    # Status
    p = sub.add_parser("status")
    p.add_argument("--base", help="Installation base path", default=str(Path.home() / f".{APP_NAME}"))
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--mode", choices=["user", "system"], default="user")

    return parser.parse_args()


def all_versions(base: Path):
    return sorted([d.name for d in base.iterdir() if d.is_dir()])


def detect_version_from_wheel(wheel_path: Path):
    # Example: mpy_tool-0.45-py3-none-any.whl → 0.45
    m = re.search(rf"{APP_NAME}-(\d+(?:\.\d+)*)", wheel_path.name)
    if not m:
        die(f"Could not auto-detect version from wheel filename '{wheel_path.name}'")
    return m.group(1)


def create_venv(venv_path: Path, python=sys.executable):
    if not venv_path.exists():
        subprocess.check_call([python, "-m", "venv", str(venv_path)])


def install_wheel(venv_path: Path, wheel: Path):
    python_exe = venv_path / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
    subprocess.check_call([str(python_exe), "-m", "pip", "install", "--upgrade", str(wheel)])


def create_launchers(base: Path, version: str, venv_path: Path, mode: str):
    """
    Create CLI launchers and Linux .desktop files.
    """
    if platform.system() == "Windows":
        bin_dir = Path.home() / "AppData" / "Local" / "Programs" / APP_NAME / "bin" \
            if mode == "user" else Path("C:/Program Files") / APP_NAME / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        for cmd in COMMANDS:
            launcher = bin_dir / f"{cmd}.bat"
            launcher.write_text(f"""@echo off
"{venv_path / 'Scripts' / 'python.exe'}" -m {APP_NAME}.{cmd} %*
""")
    else:
        bin_dir = Path.home() / ".local" / "bin" if mode == "user" else Path("/usr/local/bin")
        bin_dir.mkdir(parents=True, exist_ok=True)
        wrapper_dir = base / version / "launchers"
        wrapper_dir.mkdir(parents=True, exist_ok=True)
        for cmd in COMMANDS:
            wrapper_script = wrapper_dir / f"{cmd}.sh"
            wrapper_script.write_text(f"""#!/bin/bash
VENV_PYTHON="{venv_path / 'bin' / 'python'}"
exec "$VENV_PYTHON" -m {APP_NAME}.{cmd} "$@"
""")
            wrapper_script.chmod(0o755)
            # Symlink in bin_dir
            launcher = bin_dir / cmd
            if launcher.exists():
                launcher.unlink()
            launcher.symlink_to(wrapper_script)

        # Create .desktop files for GUI commands
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        icon_path = venv_path / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" \
            / "site-packages" / APP_NAME / "assets" / "icon.png"
        for cmd in COMMANDS:
            desktop_file = desktop_dir / f"{cmd}.desktop"
            desktop_file.write_text(f"""[Desktop Entry]
Version=1.0
Type=Application
Name=MPY_Tool
Comment=
Icon={icon_path}
Exec={bin_dir / cmd}
Terminal=false
""")
    print(f"Launchers created in {bin_dir}")


def uninstall(args):
    base = Path(args.base).resolve()
    if args.all:
        shutil.rmtree(base, ignore_errors=True)
        print("All versions removed")
        return
    if args.version:
        p = base / args.version
        if p.exists():
            shutil.rmtree(p)
            print(f"Removed version {args.version}")
        else:
            print(f"Version {args.version} not found")
    else:
        die("Specify --all or --version to uninstall")


def status(args):
    base = Path(args.base).resolve()
    versions = all_versions(base)
    if args.json:
        print(json.dumps({"versions": versions}, indent=2))
    else:
        print(f"Installed versions: {', '.join(versions) if versions else 'none'}")


def main():
    args = parse_args()
    base = Path(args.base).resolve()

    if args.command == "install":
        wheel_path = Path(args.wheel)
        if not wheel_path.exists():
            die(f"Wheel file '{wheel_path}' does not exist")

        # Auto-detect version if not provided
        version = args.version or detect_version_from_wheel(wheel_path)
        base.mkdir(parents=True, exist_ok=True)
        venv_path = base / version / "venv"

        create_venv(venv_path)
        install_wheel(venv_path, wheel_path)
        create_launchers(base, version, venv_path, args.mode)
        print(f"{APP_NAME} version {version} installed successfully")

    elif args.command == "uninstall":
        uninstall(args)

    elif args.command == "status":
        status(args)

    else:
        die(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
