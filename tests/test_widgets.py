"""Widget behaviour that needs a real Qt widget, run on the offscreen platform."""
from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no screen needed

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QWidget

from cctv_wall.i18n import Translator
from cctv_wall.models import TILES_LIMIT, Workspace
from cctv_wall.ui.ai_feed_editor import _CodePicker
from cctv_wall.ui.ai_panel import _camera_colour
from cctv_wall.ui.navigation import SiteNavigation, apply_order
from cctv_wall.ui.site_commands import delete_items


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class TestCodePicker:
    def test_kinds_side_by_side_are_not_cut_short(self):
        _app()
        picker = _CodePicker(Translator("zh_TW"), "-", "", beside_key=QWidget())
        picker.set_fields({"vdType": [("1", "公車"), ("6", "大卡車"), ("7", "腳踏車")]})
        picker.set_choice("vdType", ["1"])
        values = picker._values
        metrics = values.fontMetrics()
        for row in range(values.count()):
            item = values.item(row)
            assert item.sizeHint().width() > metrics.horizontalAdvance(item.text())
        assert picker.values() == ["1"]


class TestCameraColours:
    def test_a_page_never_shows_two_tiles_in_one_colour(self):
        for shown in (4, 8, 9, TILES_LIMIT):
            assert len({_camera_colour(index, shown) for index in range(shown)}) == shown


class _FirstEntryMenu(QMenu):
    """Patching exec on QMenu itself does not reach the C++ call; a Python subclass does."""

    def exec(self, *_arguments):
        self.actions()[0].trigger()


class TestSitePicking:
    """Ctrl and Shift on the main window's site list work as they do in the settings window."""

    def _navigation(self):
        _app()
        workspace = Workspace.from_raw({"sites": [
            {"name": name, "cameras": [{"url": f"rtsp://10.0.{site}.{camera}/s"} for camera in (1, 2, 3)]}
            for site, name in enumerate(("A", "B"))]})
        picks: list[tuple] = []
        self.deleted: list[tuple] = []
        # Like the window: a moved workspace is saved and handed straight back to the list.
        navigation = SiteNavigation(lambda _name: None, lambda: None, lambda _a, _s: None,
                                    Translator("en"), lambda _s, _c: None,
                                    lambda order: navigation.set_workspace(apply_order(navigation._workspace, order)),
                                    lambda _a, _s, _i: None, picks.append,
                                    lambda sites, cameras: self.deleted.append((sites, cameras)))
        navigation.resize(260, 600)
        navigation.set_workspace(workspace)
        navigation.show()
        navigation.activateWindow()   # shortcuts only reach an active window
        QTest.qWaitForWindowActive(navigation)
        return navigation, navigation._sites, picks

    def test_alt_arrows_move_the_selected_cameras_together(self):
        navigation, tree, _picks = self._navigation()
        self._click(tree, tree.topLevelItem(0).child(0), Qt.KeyboardModifier.ControlModifier)
        self._click(tree, tree.topLevelItem(0).child(1), Qt.KeyboardModifier.ControlModifier)
        tree.setFocus()
        QTest.keyClick(tree, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
        hosts = [camera.label.split("/")[2] for camera in navigation._workspace.site("A").cameras]
        assert hosts == ["10.0.0.3", "10.0.0.1", "10.0.0.2"]
        assert navigation._selected_cameras() == (("A", 1), ("A", 2))   # still selected: press again
        QTest.keyClick(tree, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)   # already at the bottom
        assert navigation._selected_cameras() == (("A", 1), ("A", 2))

    def test_alt_arrows_move_the_current_site(self):
        navigation, tree, _picks = self._navigation()
        self._click(tree, tree.topLevelItem(1))
        tree.setFocus()
        QTest.keyClick(tree, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
        assert navigation._workspace.site_names == ("B", "A")

    def test_delete_hands_the_selection_to_the_window(self):
        _navigation, tree, _picks = self._navigation()
        self._click(tree, tree.topLevelItem(0).child(2), Qt.KeyboardModifier.ControlModifier)
        self._click(tree, tree.topLevelItem(1).child(0), Qt.KeyboardModifier.ControlModifier)
        tree.setFocus()
        QTest.keyClick(tree, Qt.Key.Key_Delete)
        assert self.deleted == [((), (("A", 2), ("B", 0)))]

    def test_a_reorder_keeps_what_the_list_does_not_know_about(self):
        """The list's copy of the workspace lags the window's (here: the site on screen and the
        page size); a move must reorder the window's workspace, not hand the old copy back."""
        listed = Workspace.from_raw({"sites": [{"name": "A"}, {"name": "B"}], "last_site": "A"})
        current = listed.with_last_site("B").with_tiles_per_page(9)
        moved = apply_order(current, (("B", ()), ("A", ())))
        assert moved.site_names == ("B", "A")
        assert (moved.active_site.name, moved.tiles_per_page) == ("B", 9)
        assert apply_order(current, (("A", ()),)) is None   # a list out of date changes nothing

    def test_delete_items_asks_once_then_removes_sites_and_cameras(self):
        _app()
        workspace = Workspace.from_raw({"sites": [
            {"name": name, "cameras": [{"url": f"rtsp://10.0.{site}.{camera}/s"} for camera in (1, 2, 3)]}
            for site, name in enumerate(("A", "B", "C"))]})
        yes, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
        with mock.patch.object(QMessageBox, "question", return_value=no) as asked:
            assert delete_items(None, workspace, Translator("en"), ["C"], [("A", 0)]) is None
        assert asked.call_count == 1
        with mock.patch.object(QMessageBox, "question", return_value=yes):
            updated = delete_items(None, workspace, Translator("en"), ["C"], [("A", 0), ("A", 2)])
        assert updated.site_names == ("A", "B")
        assert [camera.label for camera in updated.site("A").cameras] == ["rtsp://10.0.0.2/s"]

    @staticmethod
    def _click(tree, item, modifier=Qt.KeyboardModifier.NoModifier):
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, modifier,
                         tree.visualItemRect(item).center())

    def test_shift_selects_the_range_across_sites(self):
        navigation, tree, _picks = self._navigation()
        self._click(tree, tree.topLevelItem(0).child(1))
        self._click(tree, tree.topLevelItem(1).child(0), Qt.KeyboardModifier.ShiftModifier)
        assert navigation._selected_cameras() == (("A", 1), ("A", 2), ("B", 0))

    def test_ctrl_on_a_site_toggles_all_its_cameras(self):
        navigation, tree, _picks = self._navigation()
        self._click(tree, tree.topLevelItem(1).child(2), Qt.KeyboardModifier.ControlModifier)
        self._click(tree, tree.topLevelItem(0), Qt.KeyboardModifier.ControlModifier)
        assert navigation._selected_cameras() == (("A", 0), ("A", 1), ("A", 2), ("B", 2))
        self._click(tree, tree.topLevelItem(0), Qt.KeyboardModifier.ControlModifier)
        assert navigation._selected_cameras() == (("B", 2),)

    def test_selecting_does_not_play_until_the_menu_says_so(self):
        navigation, tree, picks = self._navigation()
        first, last = tree.topLevelItem(0).child(0), tree.topLevelItem(1).child(1)
        self._click(tree, first, Qt.KeyboardModifier.ControlModifier)
        self._click(tree, last, Qt.KeyboardModifier.ControlModifier)
        assert picks == []
        point = tree.visualItemRect(last).center()
        # The right-click itself must leave the selection alone; the menu is stubbed to pick
        # its first entry instead of waiting for a user.
        with mock.patch("cctv_wall.ui.navigation.QMenu", _FirstEntryMenu):
            QTest.mouseClick(tree.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, point)
            navigation._show_context_menu(point)
        assert picks[-1] == (("A", 0), ("B", 1))
