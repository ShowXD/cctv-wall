"""掉線重連的退避節奏，以及畫格下方 AI 結果條的重繪成本。

退避只測與 Qt 無關的計數邏輯：這裡要守住的規則是「多久重試一次」，不是 widget 行為。
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # 不需要螢幕也能建立 widget

from PySide6.QtWidgets import QApplication

from cctv_wall.i18n import Translator
from cctv_wall.player import PlaybackState
from cctv_wall.ui.view_mode import ViewMode
from cctv_wall.ui.wall import (DEAD_STATES, MAX_RECONNECT_BACKOFF_TICKS, WallView, _AiLine, _Tile,
                               _due_for_retry, _release_detached)


def _tile() -> _Tile:
    # view 在這些測試裡不會被觸碰，所以不需要真的 Qt widget。
    return _Tile(view=None, log_label="camera-1")


def _retry_ticks(count: int) -> list[bool]:
    """連續 count 次稽核中，哪幾次真的觸發重連。"""
    tile = _tile()
    return [_due_for_retry(tile) for _ in range(count)]


class TestBackoff:
    def test_gaps_between_attempts_grow(self):
        # 第一次立刻重試，之後間隔 1、2、4 次稽核（5、10、20 秒）。
        assert _retry_ticks(9) == [True, False, True, False, False,
                                   True, False, False, False]

    def test_the_gap_stops_growing_at_the_ceiling(self):
        tile = _tile()
        for _ in range(60):
            _due_for_retry(tile)
        assert tile.backoff_ticks == MAX_RECONNECT_BACKOFF_TICKS

    def test_recovery_makes_the_next_outage_reconnect_at_once(self):
        tile = _tile()
        for _ in range(20):
            _due_for_retry(tile)
        tile.reset_backoff()
        assert _due_for_retry(tile) is True


class TestReleaseDetached:
    def test_a_surface_qt_already_destroyed_at_quit_is_not_an_error(self):
        # 關閉程式時 Qt 可能先刪掉無 parent 的畫格，背景釋放執行緒不能因此丟例外。
        def gone():
            raise RuntimeError("Internal C++ object (VideoTile) already deleted.")
        released = []
        tile = _Tile(view=SimpleNamespace(deleteLater=gone), log_label="camera-1",
                     player=SimpleNamespace(release=lambda: released.append(True)))
        _release_detached([tile])
        assert released == [True] and tile.player is None


class TestDeadStates:
    def test_every_other_state_triggers_a_reconnect(self):
        """OPENING 不算斷線：低階電腦連線慢，重連會打斷一個其實正在成功的協商。"""
        assert DEAD_STATES == {PlaybackState.ERROR, PlaybackState.ENDED, PlaybackState.IDLE}


class TestOutageNotice:
    def _message(self, tile: _Tile, retried: bool) -> str:
        stub = SimpleNamespace(_translator=Translator("en"))
        return WallView._outage_message(stub, tile, "no_video", retried)

    def test_a_waiting_tile_names_itself_and_its_countdown(self):
        tile = _tile()
        tile.ticks_until_retry = 4
        message = self._message(tile, retried=False)
        assert message.startswith("camera-1\n")
        assert "20s" in message

    def test_a_tile_being_retried_says_so_instead(self):
        assert "Reconnecting" in self._message(_tile(), retried=True)


class TestAiLine:
    def test_a_lit_line_is_not_restyled_by_each_new_result(self):
        # 每次 setStyleSheet 都會重新解析全站樣式表；AI 端每秒送好幾筆，低階電腦會吃不消。
        _app = QApplication.instance() or QApplication([])   # 變數撐住它，widget 才能存在
        line = _AiLine()
        styled = []
        line.setStyleSheet = lambda sheet: styled.append(sheet)
        line.show_result("12:00:00  a", "#e5534b")
        line.show_result("12:00:01  b", "#e5534b")
        line.show_result("12:00:02  c", "#e5534b")
        assert len(styled) == 1 and line.text() == "12:00:02  c"
        line.show_result("12:00:03  d", "#3fb950")   # 換顏色就要重設
        assert len(styled) == 2


class TestViewMode:
    def test_the_default_shows_every_piece_of_chrome(self):
        view = ViewMode()
        assert view.chrome_visible and not view.grips_visible

    def test_filling_the_wall_hides_chrome_and_shows_the_grips(self):
        view = ViewMode().toggle_filled()
        assert view.filled and not view.chrome_visible and view.grips_visible

    def test_fullscreen_hides_chrome_without_the_grips(self):
        view = ViewMode().enter_fullscreen(was_maximized=True)
        assert not view.chrome_visible and not view.grips_visible

    def test_leaving_fullscreen_returns_to_a_normal_wall(self):
        assert ViewMode().enter_fullscreen(False).exit_fullscreen() == ViewMode()

    def test_leaving_fullscreen_while_filled_stays_immersive(self):
        view = ViewMode().toggle_filled().enter_fullscreen(False).exit_fullscreen()
        assert view.filled and not view.chrome_visible and view.grips_visible
