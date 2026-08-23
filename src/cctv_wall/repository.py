"""Reading and writing workspace.json — the app's memory between runs.

The only module that touches the disk. Everything above it works on Workspace
objects, so moving to SQLite or a server would mean replacing this file alone.

Saving is atomic (write a temp file, then replace) so a crash or a full disk
cannot leave the user with a truncated camera list.

Camera passwords are the one field that does not round-trip verbatim: they are
encrypted for the current Windows user on the way out, decrypted on the way in.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from cctv_wall import credentials
from cctv_wall.models import Workspace

CONFIG_ENV_VAR = "CCTV_WALL_CONFIG"
CONFIG_FILENAME = "workspace.json"


class WorkspaceError(RuntimeError):
    """The stored workspace could not be read or written, with the reason attached."""


def default_config_path() -> Path:
    """Where the workspace lives: next to the exe when frozen, else the project root.

    A PyInstaller bundle unpacks into a temporary directory that is deleted on
    exit, so __file__ must not be used to locate anything the user keeps.
    """
    override = os.environ.get(CONFIG_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_FILENAME
    # src/cctv_wall/repository.py -> project root
    return Path(__file__).resolve().parents[2] / CONFIG_FILENAME


def load_workspace(path: Path | None = None) -> Workspace:
    """An empty workspace on first run; a clear error when the file is broken."""
    target = path or default_config_path()
    if not target.exists():
        return Workspace()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise WorkspaceError(f"{target.name} is not valid JSON: line {e.lineno}: {e.msg}") from e
    except OSError as e:
        raise WorkspaceError(f"cannot read {target}: {e}") from e
    if not isinstance(raw, dict):
        raise WorkspaceError(f"{target.name} must contain a JSON object")
    try:
        return Workspace.from_raw(_mapped_passwords(raw, credentials.unprotect))
    except ValueError as e:
        raise WorkspaceError(f"{target.name}: {e}") from e


def _mapped_passwords(raw: dict[str, Any], transform: Callable[[str], str]) -> dict[str, Any]:
    """A copy of the workspace mapping with every camera password passed through."""
    sites = raw.get("sites")
    if not isinstance(sites, (list, tuple)):
        return raw

    def mapped_camera(camera: Any) -> Any:
        if not isinstance(camera, dict) or not isinstance(camera.get("password"), str):
            return camera
        return {**camera, "password": transform(camera["password"])}

    def mapped_site(site: Any) -> Any:
        if not isinstance(site, dict) or not isinstance(site.get("cameras"), (list, tuple)):
            return site
        return {**site, "cameras": [mapped_camera(c) for c in site["cameras"]]}

    return {**raw, "sites": [mapped_site(s) for s in sites]}


def save_workspace(workspace: Workspace, path: Path | None = None) -> None:
    """Write atomically so an interrupted save never destroys the existing file."""
    target = path or default_config_path()
    temporary = target.with_suffix(target.suffix + ".tmp")
    stored = _mapped_passwords(workspace.as_dict(), credentials.protect)
    payload = json.dumps(stored, indent=2, ensure_ascii=False)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)
    except OSError as e:
        temporary.unlink(missing_ok=True)
        raise WorkspaceError(f"cannot write {target}: {e}") from e
