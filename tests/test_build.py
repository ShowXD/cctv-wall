"""The release builder: refuse bad requests before spending minutes on PyInstaller.

Nothing here runs PyInstaller, and RELEASES_DIRECTORY is redirected into tmp_path,
so the real dist/ tree is never touched.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from cctv_wall import build


def _request(**overrides) -> argparse.Namespace:
    request = {"label": None, "replace": False, "onefile": False, "vlc_dir": None}
    request.update(overrides)
    return argparse.Namespace(**request)


class TestReleaseName:
    @pytest.mark.parametrize("label, expected_suffix", [
        ("rc1", "rc1"),
        ("client a", "client-a"),
        ("a/b\\c:d", "a-b-c-d"),
        ("v1.2.3", "v1.2.3"),
        ("客戶 A", "客戶-A"),          # CJK counts as alphanumeric, so it survives
        ("..rc1--", "rc1"),            # leading/trailing dots and dashes are trimmed
    ])
    def test_labels_become_safe_directory_names(self, label, expected_suffix):
        assert build._release_name(label).endswith(f"-{expected_suffix}")

    def test_a_label_without_letters_or_numbers_is_rejected(self):
        with pytest.raises(ValueError, match="must contain a letter or number"):
            build._release_name("..--..")

    def test_no_label_falls_back_to_a_timestamp(self):
        name = build._release_name(None)
        assert name.startswith("CCTVWall-")
        assert name.rsplit("-", 2)[-2].isdigit()  # …-YYYYMMDD-HHMMSS


class TestSpecEnvironment:
    """The spec file cannot take arguments, so flags have to arrive as variables."""

    def test_flags_are_translated_for_the_spec(self, tmp_path):
        environment = build._spec_environment(_request(onefile=True, vlc_dir=tmp_path))
        assert environment[build.ONEFILE_VAR] == "1"
        assert environment[build.VLC_DIR_VAR] == str(tmp_path)

    def test_onefile_is_always_requested(self):
        """Releases ship as a single exe, so the spec is never left to guess."""
        assert build._spec_environment(_request())[build.ONEFILE_VAR] == "1"

    def test_no_vlc_directory_is_injected_unless_asked_for(self, monkeypatch):
        monkeypatch.delenv(build.VLC_DIR_VAR, raising=False)
        assert build.VLC_DIR_VAR not in build._spec_environment(_request())

    def test_the_existing_environment_is_preserved(self, monkeypatch):
        monkeypatch.setenv("SOME_UNRELATED_VARIABLE", "keep me")
        assert build._spec_environment(_request())["SOME_UNRELATED_VARIABLE"] == "keep me"

    def test_a_stale_onefile_variable_cannot_turn_it_off(self, monkeypatch):
        """The build no longer offers a folder mode, so an inherited "0" must not win."""
        monkeypatch.setenv(build.ONEFILE_VAR, "0")
        assert build._spec_environment(_request())[build.ONEFILE_VAR] == "1"


class TestPrepare:
    def test_a_missing_vlc_directory_is_rejected(self, tmp_path):
        with pytest.raises(build.BuildError, match="is not a directory"):
            build._prepare(_request(vlc_dir=tmp_path / "nope"))

    def test_an_existing_release_is_kept_unless_replace_is_given(self, monkeypatch, tmp_path):
        monkeypatch.setattr(build, "RELEASES_DIRECTORY", tmp_path)
        (tmp_path / build._release_name("rc1")).mkdir()
        with pytest.raises(build.BuildError, match="already exists"):
            build._prepare(_request(label="rc1"))

    def test_replace_removes_the_previous_release(self, monkeypatch, tmp_path):
        monkeypatch.setattr(build, "RELEASES_DIRECTORY", tmp_path)
        previous = tmp_path / build._release_name("rc1")
        (previous / "CCTVWall").mkdir(parents=True)
        (previous / "CCTVWall" / "CCTVWall.exe").write_text("stale")
        assert build._prepare(_request(label="rc1", replace=True)) == previous
        assert not previous.exists()

    def test_a_locked_file_explains_itself_instead_of_raising_oserror(self, monkeypatch, tmp_path):
        """Deleting a release fails on Windows while its exe is still running."""
        monkeypatch.setattr(build, "RELEASES_DIRECTORY", tmp_path)
        (tmp_path / build._release_name("rc1")).mkdir()

        def locked(_path: Path) -> None:
            raise OSError(32, "The process cannot access the file")

        monkeypatch.setattr(build.shutil, "rmtree", locked)
        with pytest.raises(build.BuildError, match="close any running CCTVWall.exe"):
            build._prepare(_request(label="rc1", replace=True))

    def test_a_fresh_release_directory_is_returned(self, monkeypatch, tmp_path):
        monkeypatch.setattr(build, "RELEASES_DIRECTORY", tmp_path)
        assert build._prepare(_request(label="rc1")).name == build._release_name("rc1")


def test_release_names_use_the_pyproject_version():
    import re

    from cctv_wall.build import _release_name, project_version
    assert re.fullmatch(r"\d+\.\d+\.\d+", project_version())
    assert _release_name("site-a") == f"CCTVWall-{project_version()}-site-a"
