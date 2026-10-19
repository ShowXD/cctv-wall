"""Strict timestamp sync: the parts that must hold without a GStreamer runtime present.

The runtime is an optional dependency and needs real hardware, so these tests cover the
declarations a deployed exe depends on rather than live playback.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from cctv_wall import gst_sync, sync_probe

SOURCE = Path(gst_sync.__file__).read_text(encoding="utf-8")


def _factory_with(gst: object) -> gst_sync.GStreamerSyncPlayerFactory:
    """A factory without its constructor: building one needs a real GStreamer runtime."""
    probe = gst_sync.GStreamerSyncPlayerFactory.__new__(gst_sync.GStreamerSyncPlayerFactory)
    probe._gst = gst
    return probe


def _element_factory(missing: set[str]) -> object:
    class _Factory:
        @staticmethod
        def find(name: str) -> object | None:
            return None if name in missing else object()

    return type("Gst", (), {"ElementFactory": _Factory})


class TestRequiredElements:
    def test_the_declared_list_matches_what_play_actually_builds(self):
        """--check trusts REQUIRED_ELEMENTS; a drifted list would report a false pass."""
        built = re.findall(r'_element\("([a-z0-9]+)"\)', SOURCE)
        assert built, "expected play() to build its elements through _element()"
        assert tuple(built) == gst_sync.REQUIRED_ELEMENTS

    def test_missing_elements_reports_only_what_the_runtime_lacks(self):
        probe = _factory_with(_element_factory({"d3d11videosink"}))
        assert probe.missing_elements() == ("d3d11videosink",)

    def test_no_h264_decoder_is_reported_even_when_the_base_pipeline_exists(self):
        missing = _factory_with(_element_factory({"d3d11h264dec", "avdec_h264"})).missing_elements()
        assert missing == ("H.264 decoder (d3d11h264dec or avdec_h264)",)

    def test_one_h264_decoder_is_enough(self):
        assert _factory_with(_element_factory({"d3d11h264dec"})).missing_elements() == ()


class TestFrozenRuntimePreparation:
    """The packaged exe loads GStreamer from _MEIPASS; PATH is what GLib actually reads."""

    def test_a_development_run_changes_nothing(self, monkeypatch):
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        before = dict(os.environ)
        gst_sync._prepare_frozen_runtime()
        assert dict(os.environ) == before

    def test_the_dll_directory_is_published_on_path(self, monkeypatch, tmp_path):
        """add_dll_directory does not reach GLib's g_module_open(); only PATH does."""
        binary_directory = tmp_path / "gstreamer" / "runtime" / "bin"
        binary_directory.mkdir(parents=True)
        monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(os, "add_dll_directory", lambda path: path, raising=False)
        monkeypatch.setenv("PATH", "C:\\existing")

        gst_sync._prepare_frozen_runtime()

        assert os.environ["PATH"].split(os.pathsep)[0] == str(binary_directory)
        assert "C:\\existing" in os.environ["PATH"]
        assert os.environ["PYGI_DLL_DIRS"] == str(binary_directory)


class TestDiagnosticRedaction:
    def test_gstreamer_debug_url_does_not_persist_credentials(self):
        detail = gst_sync._safe_debug_detail("source=rtsp://operator:secret@example.test/live")
        assert "secret" not in detail
        assert detail.endswith("rtsp://****@example.test/live")


class TestAuthenticationChallenge:
    def test_a_single_offer_is_used_as_is(self):
        assert sync_probe._preferred_challenge('Basic realm="cam"') == 'Basic realm="cam"'

    def test_no_challenge_yields_no_header(self):
        assert sync_probe._preferred_challenge("") == ""

    def test_repeated_headers_are_both_kept(self):
        connection = sync_probe._RtspConnection("rtsp://cam.lan/live")
        connection._buffer = bytearray(
            b'RTSP/1.0 401 Unauthorized\r\nWWW-Authenticate: Basic realm="cam"\r\n'
            b'WWW-Authenticate: Digest realm="cam", nonce="abc"\r\n\r\n')
        _status, headers, _body = connection._response()
        assert sync_probe._preferred_challenge(
            headers["www-authenticate"]).startswith("Digest ")
