"""Widget behaviour that needs a real Qt widget, run on the offscreen platform."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no screen needed

from PySide6.QtWidgets import QApplication, QWidget

from cctv_wall.i18n import Translator
from cctv_wall.ui.ai_feed_editor import _CodePicker


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
