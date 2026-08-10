"""掉線重連的退避節奏。

只測與 Qt 無關的計數邏輯：建立真正的 WallView 需要 QApplication，
而這裡要守住的規則是「多久重試一次」，不是 widget 行為。
"""
from __future__ import annotations

from cctv_wall.player import PlaybackState
from cctv_wall.ui.wall import (DEAD_STATES, MAX_RECONNECT_BACKOFF_TICKS, _Tile,
                               _due_for_retry)


def _tile() -> _Tile:
    # view 在這些測試裡不會被觸碰，所以不需要真的 Qt widget。
    return _Tile(view=None, log_label="camera-1")


def _retry_ticks(count: int) -> list[bool]:
    """連續 count 次稽核中，哪幾次真的觸發重連。"""
    tile = _tile()
    return [_due_for_retry(tile) for _ in range(count)]


class TestBackoff:
    def test_the_first_failure_reconnects_immediately(self):
        assert _due_for_retry(_tile()) is True

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


class TestDeadStates:
    def test_opening_is_never_treated_as_an_outage(self):
        """低階電腦連線慢，重連會打斷一個其實正在成功的協商。"""
        assert PlaybackState.OPENING not in DEAD_STATES
        assert PlaybackState.PLAYING not in DEAD_STATES

    def test_every_other_state_triggers_a_reconnect(self):
        assert DEAD_STATES == {PlaybackState.ERROR, PlaybackState.ENDED, PlaybackState.IDLE}
