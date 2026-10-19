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

from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from cctv_wall.i18n import Translator
from cctv_wall.models import Workspace
from cctv_wall.ui.ai_feed_editor import edit_ai_feeds


def duplicate_site(parent: QWidget, workspace: Workspace, translator: Translator,
                   site_name: str) -> Workspace | None:
    """Copy a site with all of its cameras; the copy becomes the active site."""
    source = workspace.site(site_name)
    if source is None:
        return None
    name = _unique_name(workspace, f"{source.name} {translator.t('copy_suffix')}")
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
    renamed = workspace.with_sites(replace(site, name=name) if site.name == source.name else site
                                   for site in workspace.sites)
    # Follow the rename so the wall keeps watching the same place.
    return renamed.with_last_site(name) if workspace.last_site == source.name else renamed


def delete_site(parent: QWidget, workspace: Workspace, translator: Translator,
                site_name: str) -> Workspace | None:
    source = workspace.site(site_name)
    if source is None:
        return None
    answer = QMessageBox.question(parent, translator.t("delete_site_action"),
                                  translator.t("delete_site_confirm", name=source.name))
    if answer != QMessageBox.StandardButton.Yes:
        return None
    remaining = workspace.with_sites(site for site in workspace.sites
                                     if site.name != source.name)
    active = remaining.active_site
    return remaining.with_last_site(active.name if active else "")


def edit_site_ai_feeds(parent: QWidget, workspace: Workspace, translator: Translator,
                       site_name: str) -> Workspace | None:
    """Edit the AI result connections of one site straight from the navigation."""
    source = workspace.site(site_name)
    if source is None:
        return None
    feeds = edit_ai_feeds(parent, translator, source.name, source.cameras, source.ai_feeds)
    if feeds is None or feeds == source.ai_feeds:
        return None
    return workspace.with_sites(replace(site, ai_feeds=feeds) if site.name == source.name else site
                                for site in workspace.sites)


def _unique_name(workspace: Workspace, base: str) -> str:
    """`base`, or `base 2`, `base 3`… — used where a clash must not stop the operator."""
    if workspace.site(base) is None:
        return base
    number = 2
    while workspace.site(f"{base} {number}") is not None:
        number += 1
    return f"{base} {number}"
