"""Layout and playback options — the behaviour behind the picture."""
from __future__ import annotations

import os

import pytest

from cctv_wall import layout, vlc_runtime
from cctv_wall.performance import INSTANCE_ARGS, media_options_for
from cctv_wall.player import NullPlayerFactory

RTSP_URL = "rtsp://10.0.0.5:554/stream1"
HLS_URL = "https://example.test/live.m3u8"


class TestGrid:
    @pytest.mark.parametrize("count,shape", [
        (0, (0, 0)), (1, (1, 1)), (2, (1, 2)), (4, (2, 2)),
        (5, (2, 3)), (9, (3, 3)), (10, (3, 4)), (16, (4, 4)),
    ])
    def test_shapes_are_roughly_square(self, count, shape):
        assert layout.grid_shape(count) == shape

    def test_every_grid_has_room_for_its_tiles(self):
        for count in range(1, 40):
            rows, columns = layout.grid_shape(count)
            assert rows * columns >= count


class TestPaging:
    @pytest.mark.parametrize("total,per_page,expected", [
        (0, 4, 1), (1, 4, 1), (4, 4, 1), (5, 4, 2), (12, 4, 3), (13, 4, 4),
    ])
    def test_page_counts(self, total, per_page, expected):
        assert layout.page_count(total, per_page) == expected

    def test_page_slice_selects_the_right_window(self):
        cameras = list(range(10))
        assert cameras[layout.page_slice(0, 4)] == [0, 1, 2, 3]
        assert cameras[layout.page_slice(2, 4)] == [8, 9]

    def test_page_beyond_the_end_is_empty_not_an_error(self):
        assert list(range(4))[layout.page_slice(9, 4)] == []

    def test_clamp_keeps_the_page_in_range(self):
        assert layout.clamp_page(9, 5, 4) == 1
        assert layout.clamp_page(-3, 5, 4) == 0

    def test_clamp_of_an_empty_site_is_page_zero(self):
        assert layout.clamp_page(3, 0, 4) == 0

    @pytest.mark.parametrize("per_page", [0, -1])
    def test_zero_tiles_per_page_is_rejected(self, per_page):
        with pytest.raises(ValueError, match="per_page"):
            layout.page_count(1, per_page)


class TestPlaybackOptions:
    def test_gpu_decode_and_no_audio(self):
        assert "--avcodec-hw=any" in INSTANCE_ARGS and "--no-audio" in INSTANCE_ARGS

    def test_rtsp_streams_are_forced_over_tcp(self):
        assert ":rtsp-tcp" in media_options_for(RTSP_URL, "auto")

    def test_non_rtsp_streams_are_not(self):
        assert ":rtsp-tcp" not in media_options_for(HLS_URL, "auto")

    def test_a_quality_cap_limits_adaptive_streams(self):
        assert ":adaptive-maxheight=720" in media_options_for(HLS_URL, "720p")

    def test_auto_quality_adds_no_cap(self):
        assert not any("adaptive-maxheight" in option for option in media_options_for(HLS_URL, "auto"))

    def test_shared_stream_tuning_is_carried_through(self):
        assert ":clock-jitter=0" in media_options_for(RTSP_URL, "auto")


class TestBundledVlc:
    """vlc_runtime only does something inside a PyInstaller bundle."""

    def test_does_nothing_when_not_frozen(self, monkeypatch):
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        assert vlc_runtime.configure() is None

    def test_ignores_a_bundle_without_libvlc(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
        (tmp_path / vlc_runtime.BUNDLE_SUBDIRECTORY).mkdir()
        assert vlc_runtime.bundled_vlc_dir() is None

    def test_points_python_vlc_at_the_bundled_library(self, monkeypatch, tmp_path):
        bundled = tmp_path / vlc_runtime.BUNDLE_SUBDIRECTORY
        (bundled / vlc_runtime.PLUGINS_SUBDIRECTORY).mkdir(parents=True)
        (bundled / vlc_runtime.LIBRARY_NAME).write_bytes(b"")
        monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
        for name in ("PYTHON_VLC_LIB_PATH", "PYTHON_VLC_MODULE_PATH", "VLC_PLUGIN_PATH"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(os, "add_dll_directory", lambda _path: None, raising=False)

        assert vlc_runtime.configure() == bundled
        assert os.environ["PYTHON_VLC_LIB_PATH"] == str(bundled / vlc_runtime.LIBRARY_NAME)
        assert os.environ["VLC_PLUGIN_PATH"].endswith(vlc_runtime.PLUGINS_SUBDIRECTORY)


class TestNullPlayer:
    def test_records_what_it_was_asked_to_play(self):
        player = NullPlayerFactory().create()
        player.play(RTSP_URL, (":rtsp-tcp",), 42)
        assert player.calls == [(RTSP_URL, (":rtsp-tcp",), 42)]

    def test_release_is_observable(self):
        player = NullPlayerFactory().create()
        player.release()
        assert player.released
