"""workspace.json: the memory that has to survive restarts and bad input.

Also covers where a packaged exe keeps that file, which differs from a source run.
"""
from __future__ import annotations

import json

import pytest

from cctv_wall import credentials, repository
from cctv_wall.models import Camera, Site, Workspace
from cctv_wall.repository import (WorkspaceError, default_config_path, load_workspace,
                                  save_workspace)

SAMPLE = {
    "version": 1,
    "last_site": "Taipei Office",
    "performance": "balanced",
    "geometry": "1600x900",
    "sites": [
        {"name": "Taipei Office", "cameras": [
            {"name": "Front Gate", "host": "10.0.0.5", "port": 554, "user": "admin",
             "password": "secret", "vendor": "hikvision", "stream": 2, "quality": "720p"},
            {"name": "Lobby", "host": "10.0.0.6", "vendor": "dahua"},
        ]},
        {"name": "Warehouse", "cameras": [{"name": "Clip", "url": "C:/videos/clip.mp4"}]},
    ],
}


@pytest.fixture
def config(tmp_path):
    return tmp_path / "workspace.json"


class TestLoad:
    def test_missing_file_gives_an_empty_workspace(self, config):
        workspace = load_workspace(config)
        assert workspace.sites == () and workspace.active_site is None

    def test_reads_sites_cameras_and_preferences(self, config):
        config.write_text(json.dumps(SAMPLE), encoding="utf-8")
        workspace = load_workspace(config)
        assert workspace.site_names == ("Taipei Office", "Warehouse")
        assert workspace.active_site.name == "Taipei Office"
        assert len(workspace.active_site.cameras) == 2
        assert workspace.tiles_per_page == 9   # legacy "balanced" profile
        gate = workspace.active_site.cameras[0]   # legacy host + vendor fields
        assert (gate.url, gate.user) == ("rtsp://10.0.0.5:554/Streaming/Channels/102", "admin")
        assert "host" not in gate.as_dict()
        assert workspace.geometry == "1600x900"
        assert workspace.language == "zh_TW"

    def test_language_is_loaded_and_unknown_values_fall_back_to_traditional_chinese(self, config):
        config.write_text(json.dumps({"language": "en"}), encoding="utf-8")
        assert load_workspace(config).language == "en"
        config.write_text(json.dumps({"language": "unknown"}), encoding="utf-8")
        assert load_workspace(config).language == "zh_TW"

    def test_theme_is_loaded_and_unknown_values_follow_the_system(self, config):
        config.write_text(json.dumps({"theme": "light"}), encoding="utf-8")
        assert load_workspace(config).theme == "light"
        config.write_text(json.dumps({"theme": "neon"}), encoding="utf-8")
        assert load_workspace(config).theme == "system"

    def test_broken_json_names_the_line(self, config):
        config.write_text("{ not json", encoding="utf-8")
        with pytest.raises(WorkspaceError, match="line"):
            load_workspace(config)

    def test_a_json_list_is_rejected(self, config):
        config.write_text("[]", encoding="utf-8")
        with pytest.raises(WorkspaceError, match="JSON object"):
            load_workspace(config)

    def test_a_bad_camera_is_located_precisely(self, config):
        config.write_text(json.dumps(
            {"sites": [{"name": "A", "cameras": [{"host": "h"}, {"host": "h", "port": 0}]}]}),
            encoding="utf-8")
        with pytest.raises(WorkspaceError, match=r"sites\[0\].*camera\[1\].*port"):
            load_workspace(config)


class TestSave:
    def test_round_trips_unchanged(self, config):
        save_workspace(Workspace.from_raw(SAMPLE), config)
        assert load_workspace(config) == Workspace.from_raw(SAMPLE)

    def test_writes_the_schema_version(self, config):
        save_workspace(Workspace(), config)
        payload = json.loads(config.read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert payload["language"] == "zh_TW"

    def test_leaves_no_temporary_file_behind(self, config):
        save_workspace(Workspace(sites=(Site("A", (Camera(url="C:/a.mp4"),)),)), config)
        assert list(config.parent.iterdir()) == [config]

    def test_non_ascii_site_names_survive(self, config):
        save_workspace(Workspace(sites=(Site("台北辦公室"),), last_site="台北辦公室"), config)
        assert load_workspace(config).active_site.name == "台北辦公室"


class TestConfigPath:
    def test_environment_variable_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv(repository.CONFIG_ENV_VAR, str(tmp_path / "elsewhere.json"))
        assert default_config_path() == tmp_path / "elsewhere.json"

    def test_defaults_to_the_project_root(self, monkeypatch):
        monkeypatch.delenv(repository.CONFIG_ENV_VAR, raising=False)
        monkeypatch.delattr("sys.frozen", raising=False)
        path = default_config_path()
        assert path.name == repository.CONFIG_FILENAME
        assert (path.parent / "pyproject.toml").exists()

    def test_frozen_exe_keeps_the_config_next_to_the_executable(self, monkeypatch, tmp_path):
        """PyInstaller's temp unpack dir is deleted on exit, so __file__ must not be used."""
        monkeypatch.delenv(repository.CONFIG_ENV_VAR, raising=False)
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setattr("sys.executable", str(tmp_path / "CCTVWall.exe"))
        assert default_config_path() == tmp_path / repository.CONFIG_FILENAME



def target_text(tmp_path) -> str:
    return (tmp_path / "workspace.json").read_text(encoding="utf-8")


class TestPasswordProtection:
    def _saved(self, tmp_path, password: str) -> dict:
        target = tmp_path / "workspace.json"
        site = Site(name="Office", cameras=(Camera(url="rtsp://10.0.0.5/stream1", user="admin",
                                                   password=password),))
        save_workspace(Workspace(sites=(site,)), target)
        return json.loads(target.read_text(encoding="utf-8"))

    @pytest.mark.skipif(not credentials.is_available(),
                        reason="DPAPI is Windows-only; elsewhere the password is stored as-is")
    def test_a_password_is_not_written_in_clear_text(self, tmp_path):
        stored = self._saved(tmp_path, "s3cret")
        assert stored["sites"][0]["cameras"][0]["password"].startswith(credentials.PREFIX)
        assert "s3cret" not in target_text(tmp_path)

    def test_a_saved_password_loads_back_unchanged(self, tmp_path):
        target = tmp_path / "workspace.json"
        self._saved(tmp_path, "s3cret")
        assert load_workspace(target).sites[0].cameras[0].password == "s3cret"

    def test_a_hand_written_plain_password_still_loads(self, tmp_path):
        target = tmp_path / "workspace.json"
        target.write_text(json.dumps({"sites": [{"name": "Office", "cameras": [
            {"host": "10.0.0.5", "password": "plain"}]}]}), encoding="utf-8")
        assert load_workspace(target).sites[0].cameras[0].password == "plain"

    def test_an_undecryptable_password_survives_a_save(self, tmp_path):
        """Another Windows account cannot read it, but saving must not erase it either."""
        target = tmp_path / "workspace.json"
        stored = f"{credentials.PREFIX}AQAAAA=="
        target.write_text(json.dumps({"sites": [{"name": "Office", "cameras": [
            {"host": "10.0.0.5", "password": stored}]}]}), encoding="utf-8")
        save_workspace(load_workspace(target), target)
        saved = json.loads(target.read_text(encoding="utf-8"))
        assert saved["sites"][0]["cameras"][0]["password"] == stored

    def test_an_empty_password_stays_empty(self, tmp_path):
        stored = self._saved(tmp_path, "")
        assert stored["sites"][0]["cameras"][0]["password"] == ""


class TestTilesPerPage:
    @pytest.mark.parametrize("legacy,tiles", [("full", 16), ("x", 4)])
    def test_a_legacy_profile_becomes_a_tile_count(self, legacy, tiles):
        assert Workspace.from_raw({"performance": legacy}).tiles_per_page == tiles

    def test_page_size_is_clamped_to_one_through_thirty_six(self):
        assert Workspace.from_raw({"tiles_per_page": 99}).tiles_per_page == 36
        assert Workspace().with_tiles_per_page(0).tiles_per_page == 1

    def test_an_old_configurable_cap_is_ignored(self):
        workspace = Workspace.from_raw({"tiles_per_page": 20, "max_tiles": 9})
        assert workspace.tiles_per_page == 20 and "max_tiles" not in workspace.as_dict()

    def test_round_trip_drops_the_legacy_key(self):
        raw = Workspace.from_raw({"performance": "full"}).as_dict()
        assert "performance" not in raw and raw["tiles_per_page"] == 16


class TestSidebarPreference:
    def test_width_and_visibility_survive_a_round_trip(self):
        workspace = Workspace().with_sidebar(420, False)
        assert Workspace.from_raw(workspace.as_dict()) == workspace

    @pytest.mark.parametrize("raw,expected", [("wide", 260), (40, 160), (5000, 800)])
    def test_a_bad_width_falls_back_or_is_clamped(self, raw, expected):
        assert Workspace.from_raw({"sidebar_width": raw}).sidebar_width == expected
