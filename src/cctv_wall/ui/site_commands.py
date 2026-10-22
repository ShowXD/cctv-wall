"""Site and camera commands from the sidebar: ask the operator, return a new Workspace.

Site commands share one shape — (parent, workspace, translator, site_name) ->
Workspace | None — so the window can dispatch them from a table instead of a
branch per action; camera commands also take the camera's index. None means nothing
should change: a cancelled dialog, a missing site, or a name that is already taken.

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
    """Edit one site's AI connections; asked to, copy its tile rows to every site."""
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


DELETE_LIST_LIMIT = 15   # names listed in the confirmation; the count covers the rest


def delete_items(parent: QWidget, workspace: Workspace, translator: Translator,
                 site_names: Iterable[str], cameras: Iterable[tuple[str, int]]) -> Workspace | None:
    """Delete sites and cameras selected in the list after one confirmation naming them all.
    The list saves at once, with no Cancel to fall back on, so this question is never skipped."""
    site_names = [name for name in site_names if workspace.site(name) is not None]
    cameras = [(name, index) for name, index in cameras if name not in site_names
               and workspace.site(name) is not None and 0 <= index < len(workspace.site(name).cameras)]
    items = [translator.t("delete_site_item", name=name) for name in site_names]
    items += [workspace.site(name).cameras[index].label for name, index in cameras]
    if not items:
        return None
    listed = items[:DELETE_LIST_LIMIT] + (["…"] if len(items) > DELETE_LIST_LIMIT else [])
    answer = QMessageBox.question(parent, translator.t("delete_selected"),
                                  translator.t("delete_selected_confirm", count=len(items),
                                               items="\n".join(listed)))
    if answer != QMessageBox.StandardButton.Yes:
        return None
    updated = workspace
    for name in site_names:
        updated = updated.without_site(name)
    doomed = set(cameras)
    for name in dict.fromkeys(name for name, _index in cameras):
        kept = [camera for index, camera in enumerate(updated.site(name).cameras)
                if (name, index) not in doomed]
        updated = _with_cameras(updated, name, kept)
    return updated


def _with_cameras(workspace: Workspace, site_name: str, cameras: Iterable[Camera]) -> Workspace:
    """Raises ValueError when the site rejects them (e.g. duplicate names with AI connections)."""
    return workspace.with_site(site_name, workspace.site(site_name).with_cameras(cameras))
