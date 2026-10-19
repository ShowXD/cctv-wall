"""Model validation and URL building — the rules everything else trusts."""
from __future__ import annotations

from dataclasses import replace

import pytest

from cctv_wall import vendors
from cctv_wall.models import Camera, Site, Workspace
from cctv_wall.urls import (MASK, build_url, direct_url_with_stream, display_url,
                           redact, stream_from_direct_url)


RTSP = "rtsp://10.0.0.5:554/stream1"


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
    def test_needs_a_url(self):
        with pytest.raises(ValueError, match="needs a url"):
            Camera()

    def test_is_immutable(self):
        with pytest.raises(Exception):
            Camera(url=RTSP).url = "x"  # type: ignore[misc]

    def test_label_prefers_name_then_url(self):
        assert Camera(name="Gate", url=RTSP).label == "Gate"
        assert Camera(url="C:/a.mp4").label == "C:/a.mp4"

    def test_label_never_shows_credentials_from_the_url(self):
        assert Camera(url="rtsp://admin:secret@10.0.0.9:554/s1").label == "rtsp://10.0.0.9:554/s1"

    def test_round_trip_keeps_only_the_four_fields(self):
        camera = Camera(name="Gate", url=RTSP, user="admin", password="secret")
        assert camera.as_dict() == {"name": "Gate", "url": RTSP, "user": "admin", "password": "secret"}
        assert Camera.from_raw(camera.as_dict()) == camera


class TestCredentialsInTheUrl:
    def test_pasted_credentials_move_to_their_fields(self):
        camera = Camera.from_raw({"url": "rtsp://adm%20in:p%40ss@10.0.0.5:554/stream1"})
        assert (camera.url, camera.user, camera.password) == (RTSP, "adm in", "p@ss")

    def test_explicit_fields_win_over_the_url(self):
        camera = Camera.from_raw({"url": "rtsp://old:old@10.0.0.5:554/stream1",
                                  "user": "new", "password": "pw"})
        assert (camera.url, camera.user, camera.password) == (RTSP, "new", "pw")

    def test_a_local_path_is_left_alone(self):
        assert Camera.from_raw({"url": "C:/videos/clip.mp4"}).url == "C:/videos/clip.mp4"


class TestLegacyCameras:
    """Files written before the URL-only model described cameras with RTSP fields."""

    def test_vendor_fields_become_a_url(self):
        camera = Camera.from_raw({"host": "10.0.0.5", "port": 554, "vendor": "hikvision",
                                  "stream": 2, "quality": "720p", "user": "admin", "password": "pw"})
        assert camera.url == "rtsp://10.0.0.5:554/Streaming/Channels/102"
        assert (camera.user, camera.password) == ("admin", "pw")

    def test_defaults_match_the_old_generic_vendor(self):
        assert Camera.from_raw({"host": "10.0.0.5"}).url == RTSP

    @pytest.mark.parametrize("raw,message", [
        ({"host": "h", "port": 0}, "port must be"),
        ({"host": "h", "port": "abc"}, "whole number"),
        ({"host": "h", "stream": 5}, "stream must be"),
        ({"host": "h", "vendor": "acme"}, "unknown vendor"),
        ({"host": "h", "vendor": "custom"}, "path_template"),
    ])
    def test_bad_legacy_values_are_reported(self, raw, message):
        with pytest.raises(ValueError, match=message):
            Camera.from_raw(raw)


class TestBuildUrl:
    def test_a_url_without_credentials_is_unchanged(self):
        assert build_url(Camera(url=RTSP)) == RTSP

    def test_credentials_are_url_encoded_into_the_url(self):
        assert build_url(Camera(url=RTSP, user="adm in", password="p@ss/1")) == \
            "rtsp://adm%20in:p%40ss%2F1@10.0.0.5:554/stream1"

    def test_a_local_file_never_gets_credentials(self):
        assert build_url(Camera(url="C:/a.mp4", user="x", password="y")) == "C:/a.mp4"

    def test_display_url_masks_only_the_password(self):
        shown = display_url(Camera(url=RTSP, user="admin", password="p@ss"))
        assert shown == "rtsp://admin:****@10.0.0.5:554/stream1"


class TestSiteAndWorkspace:
    def test_site_needs_a_name(self):
        with pytest.raises(ValueError, match="site needs a name"):
            Site(name="  ")

    def test_camera_errors_name_the_index(self):
        with pytest.raises(ValueError, match=r"camera\[1\]"):
            Site.from_raw({"name": "Office", "cameras": [{"url": "rtsp://a"}, {"name": "x"}]})

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
        updated = original.with_last_site("A").with_tiles_per_page(9)
        assert original.last_site == "" and original.tiles_per_page == 4
        assert updated.last_site == "A" and updated.tiles_per_page == 9


class TestCameraReplacement:
    """Backs the right-click stream switch: one tile changes, nothing else does."""

    @staticmethod
    def _workspace() -> Workspace:
        first = Camera(name="Gate", url="rtsp://10.0.0.1/stream1")
        second = Camera(name="Dock", url="rtsp://10.0.0.2/stream1")
        return Workspace(sites=(Site("Office", (first,)), Site("Depot", (second,))))

    def test_replaces_the_matching_camera_in_its_own_site(self):
        workspace = self._workspace()
        old = workspace.site("Depot").cameras[0]
        updated = workspace.with_camera_replaced(old, replace(old, url="rtsp://10.0.0.2/stream2"))
        assert updated.site("Depot").cameras[0].url.endswith("stream2")
        assert updated.site("Office").cameras == workspace.site("Office").cameras

    def test_leaves_the_original_workspace_untouched(self):
        workspace = self._workspace()
        old = workspace.site("Office").cameras[0]
        workspace.with_camera_replaced(old, replace(old, url="rtsp://x/stream3"))
        assert workspace.site("Office").cameras[0] == old

    def test_an_unknown_camera_returns_the_same_workspace(self):
        workspace = self._workspace()
        stranger = Camera(url="rtsp://192.168.9.9/stream1")
        assert workspace.with_camera_replaced(stranger, stranger) is workspace

    def test_only_the_first_of_two_identical_cameras_changes(self):
        camera = Camera(url="rtsp://10.0.0.5/stream1")
        workspace = Workspace(sites=(Site("Yard", (camera, camera)),))
        changed = replace(camera, url="rtsp://10.0.0.5/stream4")
        updated = workspace.with_camera_replaced(camera, changed)
        assert updated.site("Yard").cameras == (changed, camera)


class TestUniqueSiteName:
    def test_a_free_name_is_kept_and_a_taken_one_is_numbered(self):
        workspace = Workspace(sites=(Site("New site"), Site("New site 2")))
        assert workspace.unique_site_name("Other") == "Other"
        assert workspace.unique_site_name("New site") == "New site 3"


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
