"""Model validation and URL building — the rules everything else trusts."""
from __future__ import annotations

from dataclasses import replace

import pytest

from cctv_wall import quality, vendors
from cctv_wall.models import Camera, Site, Workspace
from cctv_wall.urls import (MASK, build_url, direct_url_with_stream, display_url,
                           is_youtube, redact, stream_from_direct_url)


def camera(**overrides) -> Camera:
    return Camera.from_raw({"host": "10.0.0.5", "port": 554, **overrides})


class TestQuality:
    def test_auto_has_no_height(self):
        assert quality.height_for("auto") is None

    def test_named_preset_has_its_height(self):
        assert quality.height_for("720p") == 720

    def test_unknown_preset_is_rejected(self):
        with pytest.raises(ValueError, match="unknown quality"):
            quality.height_for("4k")


class TestVendorPaths:
    @pytest.mark.parametrize("vendor,stream,expected", [
        ("generic", 1, "stream1"),
        ("hikvision", 1, "Streaming/Channels/101"),
        ("hikvision", 2, "Streaming/Channels/102"),
        ("dahua", 1, "cam/realmonitor?channel=1&subtype=0"),
        ("dahua", 3, "cam/realmonitor?channel=1&subtype=2"),
        ("reolink", 1, "h264Preview_01_main"),
        ("reolink", 2, "h264Preview_01_sub"),
    ])
    def test_known_vendors_render_expected_paths(self, vendor, stream, expected):
        assert vendors.render_path(vendors.template_for(vendor), stream) == expected

    def test_custom_vendor_uses_its_own_template(self):
        template = vendors.template_for("custom", "live/{stream0}/h264")
        assert vendors.render_path(template, 2) == "live/1/h264"

    def test_custom_vendor_without_template_is_rejected(self):
        with pytest.raises(ValueError, match="path_template"):
            vendors.template_for("custom", "  ")

    def test_leading_slash_is_dropped(self):
        assert vendors.render_path("/stream{stream}", 1) == "stream1"

    def test_unknown_variable_is_reported(self):
        with pytest.raises(ValueError, match="unknown variable"):
            vendors.render_path("live/{channel}", 1)


class TestCameraValidation:
    def test_needs_url_or_host(self):
        with pytest.raises(ValueError, match="url or a host"):
            Camera()

    def test_url_only_camera_is_valid(self):
        assert Camera(url="C:/videos/clip.mp4").host == ""

    @pytest.mark.parametrize("port", [0, -1, 65536])
    def test_port_out_of_range_is_rejected(self, port):
        with pytest.raises(ValueError, match="port must be"):
            camera(port=port)

    @pytest.mark.parametrize("stream", [0, 5])
    def test_stream_out_of_range_is_rejected(self, stream):
        with pytest.raises(ValueError, match="stream must be"):
            camera(stream=stream)

    def test_blank_port_falls_back_to_default(self):
        assert camera(port="").port == 554

    def test_non_numeric_port_is_an_error_not_a_default(self):
        with pytest.raises(ValueError, match="whole number"):
            camera(port="abc")

    def test_unknown_vendor_is_rejected(self):
        with pytest.raises(ValueError, match="unknown vendor"):
            camera(vendor="acme")

    def test_unknown_quality_is_rejected(self):
        with pytest.raises(ValueError, match="unknown quality"):
            camera(quality="4k")

    def test_custom_vendor_needs_a_template(self):
        with pytest.raises(ValueError, match="path_template"):
            camera(vendor="custom")

    def test_is_immutable(self):
        with pytest.raises(Exception):
            camera().port = 8554  # type: ignore[misc]

    def test_label_prefers_name_then_url_then_address(self):
        assert camera(name="Gate").label == "Gate"
        assert Camera(url="C:/a.mp4").label == "C:/a.mp4"
        assert camera().label == "10.0.0.5:554"

    def test_label_never_shows_credentials_from_the_url(self):
        assert Camera(url="rtsp://admin:secret@10.0.0.9:554/s1").label == "rtsp://10.0.0.9:554/s1"


class TestBuildUrl:
    def test_direct_url_wins_over_rtsp_fields(self):
        assert build_url(camera(url="C:/a.mp4")) == "C:/a.mp4"

    def test_assembles_host_port_and_vendor_path(self):
        assert build_url(camera(vendor="hikvision", stream=2)) == \
            "rtsp://10.0.0.5:554/Streaming/Channels/102"

    def test_credentials_are_url_encoded(self):
        assert build_url(camera(user="adm in", password="p@ss/1")) == \
            "rtsp://adm%20in:p%40ss%2F1@10.0.0.5:554/stream1"

    def test_no_credentials_means_no_at_sign(self):
        assert "@" not in build_url(camera())

    def test_display_url_masks_only_the_password(self):
        shown = display_url(camera(user="admin", password="p@ss"))
        assert shown == "rtsp://admin:****@10.0.0.5:554/stream1"
        assert "p%40ss" not in shown

    def test_display_url_of_a_file_is_unchanged(self):
        assert display_url(Camera(url="C:/a.mp4")) == "C:/a.mp4"

    def test_display_url_masks_a_password_embedded_in_a_direct_url(self):
        shown = display_url(Camera(url="rtsp://admin:p%40ss@10.0.0.5:554/stream1"))
        assert shown == "rtsp://admin:****@10.0.0.5:554/stream1"


class TestIsYouTube:
    @pytest.mark.parametrize("url", ["https://www.youtube.com/watch?v=x",
                                     "https://youtu.be/x",
                                     "https://m.youtube.com/watch?v=x"])
    def test_youtube_hosts_are_detected(self, url):
        assert is_youtube(url)

    @pytest.mark.parametrize("url", ["rtsp://10.0.0.5:554/stream1",
                                     "C:/videos/clip.mp4",
                                     "https://evil.example/youtube.com/watch?v=x"])
    def test_other_urls_are_not_youtube(self, url):
        assert not is_youtube(url)


class TestSiteAndWorkspace:
    def test_site_needs_a_name(self):
        with pytest.raises(ValueError, match="site needs a name"):
            Site(name="  ")

    def test_camera_errors_name_the_index(self):
        with pytest.raises(ValueError, match=r"camera\[1\]"):
            Site.from_raw({"name": "Office", "cameras": [{"host": "a"}, {"port": 1}]})

    def test_active_site_uses_the_remembered_name(self):
        workspace = Workspace(sites=(Site("A"), Site("B")), last_site="B")
        assert workspace.active_site.name == "B"

    def test_active_site_falls_back_to_the_first(self):
        workspace = Workspace(sites=(Site("A"), Site("B")), last_site="gone")
        assert workspace.active_site.name == "A"

    def test_active_site_of_an_empty_workspace_is_none(self):
        assert Workspace().active_site is None

    def test_duplicate_site_names_are_rejected(self):
        with pytest.raises(ValueError, match="duplicate site"):
            Workspace.from_raw({"sites": [{"name": "A"}, {"name": "A"}]})

    def test_with_helpers_do_not_mutate_the_original(self):
        original = Workspace(sites=(Site("A"),))
        updated = original.with_last_site("A").with_performance("full")
        assert original.last_site == "" and original.performance == "low_end"
        assert updated.last_site == "A" and updated.performance == "full"


class TestCameraReplacement:
    """Backs the right-click stream switch: one tile changes, nothing else does."""

    @staticmethod
    def _workspace() -> Workspace:
        first = Camera(name="Gate", host="10.0.0.1")
        second = Camera(name="Dock", host="10.0.0.2")
        return Workspace(sites=(Site("Office", (first,)), Site("Depot", (second,))))

    def test_replaces_the_matching_camera_in_its_own_site(self):
        workspace = self._workspace()
        old = workspace.site("Depot").cameras[0]
        updated = workspace.with_camera_replaced(old, replace(old, stream=2))
        assert updated.site("Depot").cameras[0].stream == 2
        assert updated.site("Office").cameras == workspace.site("Office").cameras

    def test_leaves_the_original_workspace_untouched(self):
        workspace = self._workspace()
        old = workspace.site("Office").cameras[0]
        workspace.with_camera_replaced(old, replace(old, stream=3))
        assert workspace.site("Office").cameras[0].stream == 1

    def test_an_unknown_camera_returns_the_same_workspace(self):
        workspace = self._workspace()
        stranger = Camera(host="192.168.9.9")
        assert workspace.with_camera_replaced(stranger, stranger) is workspace

    def test_only_the_first_of_two_identical_cameras_changes(self):
        camera = Camera(host="10.0.0.5")
        workspace = Workspace(sites=(Site("Yard", (camera, camera)),))
        updated = workspace.with_camera_replaced(camera, replace(camera, stream=4))
        assert [c.stream for c in updated.site("Yard").cameras] == [4, 1]


class TestDirectStreamRewrite:
    @pytest.mark.parametrize("url,expected", [
        ("rtsp://10.0.0.5:554/live/stream2", 2),
        ("rtsp://10.0.0.5:554/live?stream=3", 3),
        ("rtsp://stream1.cam.lan/live/stream2", 2),
        ("rtsp://stream1.cam.lan/live", None),
        ("rtsp://10.0.0.5:554/live", None),
    ])
    def test_only_the_path_and_query_declare_a_stream(self, url, expected):
        assert stream_from_direct_url(url) == expected

    def test_a_host_named_like_a_stream_survives_a_rewrite(self):
        assert (direct_url_with_stream("rtsp://stream1.cam.lan/live/stream2", 3)
                == "rtsp://stream1.cam.lan/live/stream3")

    def test_query_markers_are_rewritten(self):
        assert (direct_url_with_stream("rtsp://10.0.0.5:554/live?stream=1", 4)
                == "rtsp://10.0.0.5:554/live?stream=4")

    def test_local_paths_still_work(self):
        assert direct_url_with_stream(r"C:\videos\stream1.mp4", 2) == r"C:\videos\stream2.mp4"

    def test_an_unrecognised_url_is_left_alone(self):
        assert direct_url_with_stream("rtsp://10.0.0.5:554/live", 2) is None


class TestRedaction:
    def test_credentials_in_free_text_are_masked(self):
        assert redact("failed: rtsp://operator:s3cret@cam.lan/live") == (
            f"failed: rtsp://{MASK}@cam.lan/live")

    def test_credential_free_text_is_untouched(self):
        assert redact("failed: rtsp://cam.lan/live") == "failed: rtsp://cam.lan/live"
