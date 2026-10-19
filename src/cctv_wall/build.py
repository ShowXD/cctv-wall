"""Versioned PyInstaller release builds with visible progress and safe output handling."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_FILE = PROJECT_ROOT / "cctv_wall.spec"
RELEASES_DIRECTORY = PROJECT_ROOT / "dist" / "releases"
BUILD_DIRECTORY = PROJECT_ROOT / "build" / "releases"
# The spec reads these. Releases are intentionally always one-file executables.
ONEFILE_VAR = "CCTV_WALL_ONEFILE"
VLC_DIR_VAR = "CCTV_WALL_VLC_DIR"


def project_version() -> str:
    """pyproject.toml is the one place the version lives; a copy elsewhere goes stale."""
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)["project"]["version"]


class BuildError(RuntimeError):
    """The build cannot start, with a reason worth printing on its own."""


def _release_name(label: str | None) -> str:
    """Use a human-readable, collision-resistant directory name by default."""
    suffix = label.strip() if label else datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_suffix = "".join(character if character.isalnum() or character in "-_." else "-"
                          for character in suffix).strip(".-")
    if not safe_suffix:
        raise ValueError("the build label must contain a letter or number")
    return f"CCTVWall-{project_version()}-{safe_suffix}"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a complete, versioned one-file CCTV Wall release.")
    parser.add_argument("target", nargs="?", default="cctv-wall", choices=["cctv-wall"],
                        help="Release target (the only supported target is cctv-wall)")
    parser.add_argument("--label", help="Optional release label, for example rc1 or customer-a")
    parser.add_argument("--replace", action="store_true",
                        help="Delete and rebuild an existing --label output directory")
    parser.add_argument("--vlc-dir", type=Path,
                        help="VLC directory to bundle, instead of searching for one")
    return parser.parse_args()


def _spec_environment(args: argparse.Namespace) -> dict[str, str]:
    """The spec cannot take arguments, so the flags reach it as environment variables."""
    environment = dict(os.environ)
    environment[ONEFILE_VAR] = "1"
    if args.vlc_dir is not None:
        environment[VLC_DIR_VAR] = str(args.vlc_dir)
    return environment


def _remove(directory: Path) -> None:
    """Delete a previous release, explaining the one failure that actually happens."""
    print(f"[cctv-wall] removing previous build: {directory}")
    try:
        shutil.rmtree(directory)
    except OSError as error:
        raise BuildError(
            f"could not delete {directory}: {error}\n"
            "[cctv-wall] a file there is in use — close any running CCTVWall.exe "
            "(and any Explorer window showing that folder), then try again") from error


def _prepare(args: argparse.Namespace) -> Path:
    """Validate the request and clear the way, before spending minutes on a build."""
    if args.vlc_dir is not None and not args.vlc_dir.is_dir():
        raise BuildError(f"--vlc-dir {args.vlc_dir} is not a directory")
    output_directory = RELEASES_DIRECTORY / _release_name(args.label)
    if output_directory.exists():
        if not args.replace:
            raise BuildError(f"{output_directory} already exists\n"
                             "[cctv-wall] use a different --label, or pass --replace to rebuild it.")
        _remove(output_directory)
    return output_directory


def main() -> int:
    args = _arguments()
    try:
        output_directory = _prepare(args)
    except (BuildError, ValueError) as error:
        print(f"[cctv-wall] build aborted: {error}", file=sys.stderr)
        return 2
    release_name = output_directory.name
    work_directory = BUILD_DIRECTORY / release_name

    command = [
        sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm", "--clean",
        "--distpath", str(output_directory), "--workpath", str(work_directory),
    ]
    print(f"[cctv-wall] release : {release_name}")
    print("[cctv-wall] mode    : onefile (VLC + strict timestamp sync included)")
    print(f"[cctv-wall] output  : {output_directory}")
    print("[cctv-wall] building…")
    try:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True,
                       env=_spec_environment(args))
    except FileNotFoundError:
        print("[cctv-wall] PyInstaller is not installed. Run: uv sync", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as error:
        print(f"[cctv-wall] build failed with exit code {error.returncode}", file=sys.stderr)
        return error.returncode
    executable = output_directory / "CCTVWall.exe"
    print(f"[cctv-wall] complete: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
