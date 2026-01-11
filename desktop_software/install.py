#!/usr/bin/env python3
"""
Cross-platform installer/uninstaller for python wheels.
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

# -------- change this section between apps, start ----------

APP_NAME = "mpy_tool"
# List of commands to be installed as defined in the pyproject.toml file '[tool.poetry.scripts]' section
# If the second argument is defined then 'venv python -m <second arg>' is used to start the script.
# If not defined then these commands are launched using the pip/poetry startup script created when
# the python wheel is installed.
# If a command (dict key) includes the 'gui' text then on a Linux platform a .desktop file is
# created to launch the file during installation.
CMD_DICT = {"mpy_tool": "",
            "mpy_tool_gui": "mpy_tool.mpy_tool_gui",
            "mpy_tool_rshell": "",
            "mpy_tool_mpremote": ""}

# -------- change this section between apps, end ----------

def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def get_bin_dir(mode):
    system = platform.system()
    if system == "Windows":
        return (
            Path.home() / "AppData" / "Local" / "Programs" / APP_NAME / "bin"
            if mode == "user"
            else Path("C:/Program Files") / APP_NAME / "bin"
        )
    else:
        return Path.home() / ".local" / "bin" if mode == "user" else Path("/usr/local/bin")


def get_desktop_dir():
    return Path.home() / ".local" / "share" / "applications"


def get_macos_app_dir():
    return Path.home() / "Applications"   # this is where your installer puts .app

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

    # Switch
    p = sub.add_parser("switch")
    p.add_argument("version", nargs="?", help="Version to activate")
    p.add_argument("--latest", action="store_true", help="Switch to highest installed version")
    p.add_argument("--base", default=str(Path.home() / f".{APP_NAME}"))
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


def select_version(base: Path, requested: str | None, latest: bool):
    versions = all_versions(base)
    if not versions:
        die("No versions installed")

    if latest:
        return versions[-1]

    if not requested:
        die("Specify a version or --latest")

    if requested not in versions:
        die(f"Version {requested} is not installed")

    return requested


def remove_active_launchers(base: Path, mode: str):
    """
    Remove all launchers that point into ~/.mpy_tool.
    Works even if install.json is missing.
    """
    bin_dir = get_bin_dir(mode)
    system = platform.system()

    if not bin_dir.exists():
        return

    for p in bin_dir.iterdir():
        if system == "Windows" and p.suffix == ".bat":
            txt = p.read_text(errors="ignore")
            if str(base) in txt:
                p.unlink()
        else:
            if p.is_symlink():
                try:
                    if str(base) in str(p.resolve()):
                        p.unlink()
                except Exception:
                    pass


def remove_active_gui_launchers(base: Path):
    system = platform.system()

    if system == "Linux":
        d = get_desktop_dir()
        if d.exists():
            for f in d.glob("*.desktop"):
                txt = f.read_text(errors="ignore")
                if str(base) in txt:
                    f.unlink()

    if system == "Darwin":
        d = get_macos_app_dir()
        if d.exists():
            for app in d.glob("*.app"):
                shutil.rmtree(app, ignore_errors=True)


def switch_version(args):
    base = Path(args.base).resolve()
    version = select_version(base, args.version, args.latest)

    print(f"Switching {APP_NAME} to version {version}")

    # Remove current global launchers
    remove_active_launchers(base, args.mode)
    remove_active_gui_launchers(base)

    venv = base / version / "venv"
    if not venv.exists():
        die(f"Broken install: {venv} missing")

    # Recreate launchers for this version
    create_launchers(args, base, version, venv, args.mode)

    print(f"{APP_NAME} now using version {version}")


def create_venv(venv_path: Path, python=sys.executable):
    if not venv_path.exists():
        subprocess.check_call([python, "-m", "venv", str(venv_path)])


def install_wheel(venv_path: Path, wheel: Path):
    python_exe = venv_path / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
    subprocess.check_call([str(python_exe), "-m", "pip", "install", "--upgrade", str(wheel)])


def remove_launchers_for_version(base, version, mode):
    system = platform.system()
    bin_dir = get_bin_dir(mode)
    desktop_dir = get_desktop_dir()
    mac_app_dir = get_macos_app_dir()

    meta_file = base / version / "install.json"
    if not meta_file.exists():
        return

    meta = json.loads(meta_file.read_text())
    cmds = meta["commands"]

    for cmd in cmds:
        # Linux/macOS shell wrappers
        p = bin_dir / cmd
        if p.exists() or p.is_symlink():
            try:
                target = p.resolve()
                if str(base / version) in str(target):
                    p.unlink()
            except Exception:
                pass

        # Linux .desktop files
        desktop = desktop_dir / f"{cmd}.desktop"
        if desktop.exists():
            desktop.unlink()

        # macOS .app bundles
        app = mac_app_dir / f"{cmd}.app"
        if app.exists():
            shutil.rmtree(app, ignore_errors=True)


def remove_windows_launchers(mode):
    bin_dir = get_bin_dir(mode)
    if not bin_dir.exists():
        return
    for cmd in CMD_DICT:
        bat = bin_dir / f"{cmd}.bat"
        if bat.exists():
            bat.unlink()


def remove_from_user_path(dir_to_remove):
    dir_to_remove = str(dir_to_remove).lower().rstrip("\\")
    current = get_user_path()
    parts = [p for p in current.split(";") if p]

    new_parts = []
    for p in parts:
        if p.lower().rstrip("\\") != dir_to_remove:
            new_parts.append(p)

    new = ";".join(new_parts)
    if new != current:
        set_user_path(new)
        return True
    return False

def load_install_record(version_path: Path):
    f = version_path / "install.json"
    if not f.exists():
        die(f"Missing install.json in {version_path}")
    return json.loads(f.read_text())


def get_installed_commands(version_path: Path):
    """
    Return list of commands belonging to this version.
    Works even if install.json is missing.
    """
    meta = version_path / "install.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text())
            return data.get("commands", [])
        except Exception:
            pass

    # Fallback: inspect venv/bin
    venv = version_path / "venv"
    if platform.system() == "Windows":
        bin_dir = venv / "Scripts"
        exts = (".exe", ".bat", ".cmd")
    else:
        bin_dir = venv / "bin"
        exts = ("",)

    cmds = []
    if bin_dir.exists():
        for p in bin_dir.iterdir():
            for ext in exts:
                if p.name == p.stem + ext:
                    if p.stem in CMD_DICT:
                        cmds.append(p.stem)

    # Final fallback (very old installs)
    return list(CMD_DICT.keys())


def remove_version(version: str, base: Path, mode: str):
    version_path = base / version
    if not version_path.exists():
        print(f"Version {version} not found")
        return

    system = platform.system()
    bin_dir = get_bin_dir(mode)
    desktop_dir = get_desktop_dir()
    mac_app_dir = get_macos_app_dir()

    commands = get_installed_commands(version_path)

    for cmd in commands:
        # ----- CLI launchers -----
        launcher = bin_dir / cmd
        if launcher.exists() or launcher.is_symlink():
            try:
                target = launcher.resolve()
                if str(version_path) in str(target):
                    launcher.unlink()
                    print(f"Removed {launcher}")
            except Exception:
                launcher.unlink(missing_ok=True)

        # Windows .bat
        if system == "Windows":
            bat = bin_dir / f"{cmd}.bat"
            if bat.exists():
                txt = bat.read_text(errors="ignore")
                if str(version_path) in txt:
                    bat.unlink()
                    print(f"Removed {bat}")

        # Linux .desktop
        if system == "Linux":
            desktop = desktop_dir / f"{cmd}.desktop"
            if desktop.exists():
                txt = desktop.read_text(errors="ignore")
                if str(version_path) in txt:
                    desktop.unlink()
                    print(f"Removed {desktop}")

        # macOS .app
        if system == "Darwin":
            app = mac_app_dir / f"{cmd}.app"
            if app.exists():
                shutil.rmtree(app, ignore_errors=True)
                print(f"Removed {app}")

    shutil.rmtree(version_path, ignore_errors=True)
    print(f"Removed version {version}")


def uninstall(args):
    base = Path(args.base).resolve()

    if not base.exists():
        print("Nothing installed")
        return

    if args.all:
        for v in all_versions(base):
            remove_version(v, base, args.mode)
        return

    if args.version:
        remove_version(args.version, base, args.mode)
        return

    die("Specify --all or --version")


ENV_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

def get_machine_path():
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ENV_KEY) as k:
        return winreg.QueryValueEx(k, "Path")[0]


def get_user_path():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, "Path")[0]
    except FileNotFoundError:
        return ""


def set_user_path(value):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "Path", 0, winreg.REG_EXPAND_SZ, value)


def add_to_user_path(dir_to_add):
    # Ensure string
    dir_to_add = str(dir_to_add)

    current = get_user_path()

    parts = [p for p in current.split(";") if p]

    norm = [p.lower().rstrip("\\") for p in parts]
    target = dir_to_add.lower().rstrip("\\")

    if target in norm:
        return False   # already present

    new = current + (";" if current and not current.endswith(";") else "") + dir_to_add
    set_user_path(new)
    return True


def ask_reboot():
    import ctypes

    MB_ICONQUESTION = 0x20
    MB_YESNO = 0x04
    MB_DEFBUTTON2 = 0x100
    MB_SYSTEMMODAL = 0x1000

    result = ctypes.windll.user32.MessageBoxW(
        None,
        "MPY Tool has been added to your PATH.\n\n"
        "Windows needs to restart Explorer (or reboot) for this to take effect.\n\n"
        "Restart the computer now?",
        "MPY Tool installation",
        MB_ICONQUESTION | MB_YESNO | MB_DEFBUTTON2 | MB_SYSTEMMODAL
    )

    if result == 6:  # YES
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "shutdown", "/r /t 5", None, 1
        )


def create_launchers(args, base: Path, version: str, venv_path: Path, mode: str):
    """
    Create CLI launchers and Linux .desktop files.

    On Windows: creates .bat files that call the venv-installed console scripts.
    On Linux/macOS: creates wrapper scripts that either call python -m <module>
                    or the venv-installed console scripts, with symlinks in bin_dir.
    """

    system = platform.system()
    bin_dir = get_bin_dir(args.mode)
    if system == "Windows":
        bin_dir.mkdir(parents=True, exist_ok=True)

        venv_dir = str(venv_path)

        for cmd, module_target in CMD_DICT.items():
            launcher = bin_dir / f"{cmd}.bat"
            if module_target:
                launcher.write_text(
                    f"""@echo off
set VENV_DIR={venv_dir}
call "%VENV_DIR%\\Scripts\\activate.bat"
python -m {module_target} %*
""")

            else:
                launcher.write_text(
                    f"""@echo off
set VENV_DIR={venv_dir}
call "%VENV_DIR%\\Scripts\\activate.bat"
python -m {APP_NAME}.{cmd} %*
""")
            print(f"Created {launcher}")

        # Ensure the bin folder is on the system PATH
        path_changed = add_to_user_path(bin_dir)

        if path_changed:
            ask_reboot()

    else:
        # Linux / macOS
        bin_dir.mkdir(parents=True, exist_ok=True)

        wrapper_dir = base / version / "launchers"
        wrapper_dir.mkdir(parents=True, exist_ok=True)

        python_exe = venv_path / "bin" / "python"

        for cmd, module_target in CMD_DICT.items():
            if module_target:
                # Command needs python -m module
                launcher = bin_dir / cmd
                contents = f"""#!/bin/sh
exec "{python_exe}" -m {module_target} "$@"
"""
                launcher.write_text(contents)
                launcher.chmod(0o755)
            else:
                # Use the venv-installed console script
                entrypoint = venv_path / "bin" / cmd
                if not entrypoint.exists():
                    die(f"Entrypoint {cmd} not found in venv at {entrypoint}")

                wrapper_script = wrapper_dir / f"{cmd}.sh"
                wrapper_script.write_text(f"""#!/bin/sh
exec "{entrypoint}" "$@"
""")
                wrapper_script.chmod(0o755)

                launcher = bin_dir / cmd
                if launcher.exists() or launcher.is_symlink():
                    launcher.unlink()
                launcher.symlink_to(wrapper_script)

            print(f"Created {launcher}")

        # Optional: create .desktop files for GUI commands
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        # Assuming icon is in the installed package
        icon_path = venv_path / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" \
                    / "site-packages" / APP_NAME / "assets" / "icon.png"

        if system == "Linux":
            for cmd, module_target in CMD_DICT.items():
                # Only GUI apps need desktop files
                if "gui" in cmd.lower():
                    desktop_file = desktop_dir / f"{cmd}.desktop"
                    desktop_file.write_text(f"""[Desktop Entry]
Version=1.0
Type=Application
Name={cmd}
Comment=
Icon={icon_path}
Exec={bin_dir / cmd}
Terminal=false
""")
                    print(f"Created {desktop_file}")

    # Create a file to track ownership of launchers
    meta = {
        "version": version,
        "commands": list(CMD_DICT.keys())
    }
    meta_file = base / version / "install.json"
    meta_file.write_text(json.dumps(meta, indent=2))


def current_link(base):
    return base / "current"


def get_current_version(base):
    p = current_link(base)
    if not p.exists():
        return None

    if p.is_symlink():
        return p.resolve().name
    else:
        return p.read_text().strip()

def set_current_version(base, version):
    p = current_link(base)
    target = base / version

    if platform.system() == "Windows":
        p.write_text(version)
    else:
        if p.exists() or p.is_symlink():
            p.unlink()
        p.symlink_to(target)


def status(args):
    base = Path(args.base).resolve()
    versions = all_versions(base)
    current = get_current_version(base)

    if args.json:
        print(json.dumps({
            "current": current,
            "installed": versions
        }, indent=2))
        return

    if not versions:
        print("No versions installed")
        return

    print("Installed versions:")
    for v in versions:
        if v == 'current':
            continue
        mark = "*" if v == current else " "
        print(f" {mark} {v}")


def ensure_pip(venv_path: Path):
    python_exe = venv_path / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
    try:
        subprocess.check_call([str(python_exe), "-m", "pip", "--version"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        print("Installing pip into virtualenv...")
        subprocess.check_call([str(python_exe), "-m", "ensurepip", "--upgrade"])
        subprocess.check_call([str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

def install(args):
    base = Path(args.base).resolve()
    wheel_path = Path(args.wheel)
    if not wheel_path.exists():
        die(f"Wheel file '{wheel_path}' does not exist")

    # Auto-detect version if not provided
    version = args.version or detect_version_from_wheel(wheel_path)
    base.mkdir(parents=True, exist_ok=True)
    venv_path = base / version / "venv"

    create_venv(venv_path)
    ensure_pip(venv_path)
    install_wheel(venv_path, wheel_path)
    create_launchers(args, base, version, venv_path, args.mode)
    set_current_version(base, version)
    print(f"{APP_NAME} version {version} installed successfully")


def main():
    args = parse_args()

    if args.command == "install":
        install(args)

    elif args.command == "uninstall":
        uninstall(args)

    elif args.command == "status":
        status(args)

    elif args.command == "switch":
        switch_version(args)

    else:
        die(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
