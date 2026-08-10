"""workspace.json: the memory that has to survive restarts and bad input.

Also covers where a packaged exe keeps that file, which differs from a source run.
"""
from __future__ import annotations

import json

import pytest

from cctv_wall import repository
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
        assert workspace.performance == "balanced"
        assert workspace.geometry == "1600x900"
        assert workspace.language == "zh_TW"

    def test_language_is_loaded_and_unknown_values_fall_back_to_traditional_chinese(self, config):
        config.write_text(json.dumps({"language": "en"}), encoding="utf-8")
        assert load_workspace(config).language == "en"
        config.write_text(json.dumps({"language": "unknown"}), encoding="utf-8")
        assert load_workspace(config).language == "zh_TW"

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

    def test_the_environment_variable_still_wins_when_frozen(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setenv(repository.CONFIG_ENV_VAR, str(tmp_path / "pinned.json"))
        assert default_config_path() == tmp_path / "pinned.json"

