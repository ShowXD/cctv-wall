"""Site-level workspace commands: ask the operator, return a new Workspace.

Every command has the same shape — (parent, workspace, translator, site_name) ->
Workspace | None — so the window can dispatch them from a table instead of a
branch per action. None means nothing should change: a cancelled dialog, a missing
site, or a name that is already taken.

The caller owns persistence and reloading, so none of this needs a video wall on
screen to be exercised. Kept out of MainWindow because it touches neither.
"""
from __future__ import annotations

from dataclasses import replace

from collections.abc import Iterable

from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from cctv_wall.i18n import Translator
from cctv_wall.models import Camera, Workspace
from cctv_wall.ui.ai_feed_editor import edit_ai_feeds
from cctv_wall.ui.camera_form import edit_camera


def duplicate_site(parent: QWidget, workspace: Workspace, translator: Translator,
                   site_name: str) -> Workspace | None:
    """Copy a site with all of its cameras; the copy becomes the active site."""
    source = workspace.site(site_name)
    if source is None:
        return None
    name = workspace.unique_site_name(f"{source.name} {translator.t('copy_suffix')}")
    return workspace.with_sites((*workspace.sites,
                                 replace(source, name=name))).with_last_site(name)


def rename_site(parent: QWidget, workspace: Workspace, translator: Translator,
                site_name: str) -> Workspace | None:
    source = workspace.site(site_name)
    if source is None:
        return None
    name, accepted = QInputDialog.getText(parent, translator.t("rename_site"),
                                          translator.t("new_site_name"), text=source.name)
    name = name.strip()
    if not accepted or not name or name == source.name:
        return None
    if workspace.site(name) is not None:
        # Site names identify a place: explain the clash instead of silently merging.
        QMessageBox.warning(parent, translator.t("rename_site"),
                            translator.t("site_exists", name=name))
        return None
    return workspace.with_site(source.name, replace(source, name=name))


def delete_site(parent: QWidget, workspace: Workspace, translator: Translator,
                site_name: str) -> Workspace | None:
    source = workspace.site(site_name)
    if source is None:
        return None
    answer = QMessageBox.question(parent, translator.t("delete_site_action"),
                                  translator.t("delete_site_confirm", name=source.name))
    if answer != QMessageBox.StandardButton.Yes:
        return None
    return workspace.without_site(source.name)


def edit_site_ai_feeds(parent: QWidget, workspace: Workspace, translator: Translator,
                       site_name: str) -> Workspace | None:
    """Edit the AI result connections of one site straight from the navigation."""
    source = workspace.site(site_name)
    if source is None:
        return None
    edited = edit_ai_feeds(parent, translator, source.name, source.cameras, source.ai_feeds)
    if edited is None:
        return None
    feeds, tile_rows_for_all_sites = edited
    updated = workspace.with_site(source.name, replace(source, ai_feeds=feeds))
    if tile_rows_for_all_sites is not None:
        updated = updated.with_ai_tile_rows(*tile_rows_for_all_sites)
    return None if updated == workspace else updated


def add_camera(parent: QWidget, workspace: Workspace, translator: Translator,
               site_name: str) -> Workspace | None:
    """Add one camera to a site from a small dialog, without opening the whole settings window."""
    site = workspace.site(site_name)
    if site is None:
        return None
    return edit_camera(parent, translator, None,
                       lambda camera: _with_cameras(workspace, site_name, (*site.cameras, camera)))


# Camera commands also receive the camera's position within its site.

def edit_camera_at(parent: QWidget, workspace: Workspace, translator: Translator,
                   site_name: str, index: int) -> Workspace | None:
    site = workspace.site(site_name)
    if site is None or not 0 <= index < len(site.cameras):
        return None
    before, after = site.cameras[:index], site.cameras[index + 1:]
    return edit_camera(parent, translator, site.cameras[index],
                       lambda camera: _with_cameras(workspace, site_name, (*before, camera, *after)))


def delete_camera_at(parent: QWidget, workspace: Workspace, translator: Translator,
                     site_name: str, index: int) -> Workspace | None:
    site = workspace.site(site_name)
    if site is None or not 0 <= index < len(site.cameras):
        return None
    answer = QMessageBox.question(parent, translator.t("delete_camera"),
                                  translator.t("delete_camera_confirm", name=site.cameras[index].label))
    if answer != QMessageBox.StandardButton.Yes:
        return None
    return _with_cameras(workspace, site_name, site.cameras[:index] + site.cameras[index + 1:])


def _with_cameras(workspace: Workspace, site_name: str, cameras: Iterable[Camera]) -> Workspace:
    """Raises ValueError when the site rejects them (e.g. duplicate names with AI connections)."""
    return workspace.with_site(site_name, workspace.site(site_name).with_cameras(cameras))
