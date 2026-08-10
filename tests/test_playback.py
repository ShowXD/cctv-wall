"""Layout, performance options and resolvers — the behaviour behind the picture."""
from __future__ import annotations

import os

import pytest

from cctv_wall import layout, vlc_runtime
from cctv_wall.performance import (BALANCED, FULL, LOW_END, PerformanceProfile,
                                  media_options_for, profile_for)
from cctv_wall.player import NullPlayerFactory
from cctv_wall.resolvers import (PassthroughResolver, ResolveError, ResolverChain,
                                 YouTubeResolver)

RTSP_URL = "rtsp://10.0.0.5:554/stream1"
HLS_URL = "https://example.test/live.m3u8"
YOUTUBE_URL = "https://www.youtube.com/watch?v=abc"


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


class TestPerformanceProfiles:
    def test_low_end_is_the_default_and_the_fallback(self):
        assert profile_for("nonsense") is LOW_END
        assert profile_for("balanced") is BALANCED

    def test_tile_budget_grows_with_the_profile(self):
        assert LOW_END.tiles_per_page < BALANCED.tiles_per_page < FULL.tiles_per_page

    def test_low_end_uses_gpu_decode_and_skips_the_loop_filter(self):
        assert "--avcodec-hw=any" in LOW_END.instance_args
        assert ":avcodec-skiploopfilter=all" in LOW_END.stream_options

    def test_a_profile_must_allow_at_least_one_tile(self):
        with pytest.raises(ValueError, match="tiles_per_page"):
            PerformanceProfile("x", (), (), 0, False)

    def test_rtsp_streams_are_forced_over_tcp(self):
        assert ":rtsp-tcp" in media_options_for(RTSP_URL, "auto", LOW_END)

    def test_non_rtsp_streams_are_not(self):
        assert ":rtsp-tcp" not in media_options_for(HLS_URL, "auto", LOW_END)

    def test_a_quality_cap_limits_adaptive_streams(self):
        assert ":adaptive-maxheight=720" in media_options_for(HLS_URL, "720p", FULL)

    def test_auto_quality_adds_no_cap(self):
        assert not any("adaptive-maxheight" in option
                       for option in media_options_for(HLS_URL, "auto", FULL))

    def test_audio_is_disabled_unless_the_profile_allows_it(self):
        assert ":no-audio" in media_options_for(RTSP_URL, "auto", LOW_END)
        assert ":no-audio" not in media_options_for(RTSP_URL, "auto", FULL)

    def test_profile_options_are_carried_through(self):
        assert ":clock-jitter=0" in media_options_for(RTSP_URL, "auto", LOW_END)


class StubResolver:
    """Claims one exact URL, so chain ordering can be observed."""

    def __init__(self, url: str, result: str) -> None:
        self._url = url
        self._result = result
        self.calls = 0

    def handles(self, url: str) -> bool:
        return url == self._url

    def resolve(self, url: str, quality: str) -> str:
        self.calls += 1
        return self._result


class TestResolvers:
    def test_passthrough_returns_the_url_untouched(self):
        assert PassthroughResolver().resolve(RTSP_URL, "720p") == RTSP_URL

    def test_youtube_resolver_only_claims_youtube(self):
        resolver = YouTubeResolver()
        assert resolver.handles(YOUTUBE_URL)
        assert not resolver.handles(RTSP_URL)

    def test_youtube_format_caps_the_height(self):
        assert "[height<=720]" in YouTubeResolver._format("720p")

    def test_youtube_format_without_a_cap_asks_for_best(self):
        assert YouTubeResolver._format("auto") == "best[protocol^=http]/best/best"

    def test_an_unrunnable_executable_is_reported_clearly(self, tmp_path):
        missing = tmp_path / "not-really-yt-dlp.exe"
        with pytest.raises(ResolveError, match="could not run yt-dlp"):
            YouTubeResolver(executable=str(missing)).resolve(YOUTUBE_URL, "auto")

    def test_without_a_cli_it_falls_back_to_the_library(self, monkeypatch):
        """A frozen exe has no yt-dlp on PATH, only the importable module."""
        monkeypatch.setattr("shutil.which", lambda _name: None)
        calls = []
        monkeypatch.setattr(YouTubeResolver, "_resolve_with_library",
                            lambda self, url, quality: calls.append((url, quality)) or "stream")
        assert YouTubeResolver().resolve(YOUTUBE_URL, "720p") == "stream"
        assert calls == [(YOUTUBE_URL, "720p")]

    def test_the_first_matching_resolver_wins(self):
        first = StubResolver(RTSP_URL, "first")
        second = StubResolver(RTSP_URL, "second")
        assert ResolverChain((first, second)).resolve(RTSP_URL, "auto") == "first"
        assert second.calls == 0

    def test_passthrough_last_handles_everything_else(self):
        chain = ResolverChain((StubResolver(YOUTUBE_URL, "yt"), PassthroughResolver()))
        assert chain.resolve(HLS_URL, "auto") == HLS_URL

    def test_an_unhandled_url_is_an_error(self):
        with pytest.raises(ResolveError, match="no resolver"):
            ResolverChain((StubResolver(YOUTUBE_URL, "yt"),)).resolve(RTSP_URL, "auto")

    def test_an_empty_chain_is_rejected(self):
        with pytest.raises(ValueError, match="at least one"):
            ResolverChain(())


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

    def test_release_and_mute_are_observable(self):
        player = NullPlayerFactory().create()
        player.set_muted(True)
        player.release()
        assert player.muted and player.released
