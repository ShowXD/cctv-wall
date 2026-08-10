"""Entry point: build the collaborators, hand them to the window, run the loop.

The only place that knows the real implementations. Everything else takes them as
arguments, which is what keeps the rest of the package testable.

`--dry-run` builds the whole GUI with a fake playback backend and exits — useful
for checking a machine without VLC installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from cctv_wall.event_log import configure as configure_log, logger
from cctv_wall.repository import (WorkspaceError, default_config_path, load_workspace,
                                  save_workspace)
from cctv_wall.ui.startup import StartupProgress
from cctv_wall.ui.theme import application_style
from cctv_wall.vlc_runtime import configure as configure_vlc

VLC_HINT = ("Install the VLC desktop app matching your Python's bitness (64-bit Python "
            "needs 64-bit VLC), then run `uv sync`.")


def _factory_builder(dry_run: bool):
    """Choose the playback backend once, so nothing downstream has to care."""
    if dry_run:
        from cctv_wall.player import NullPlayerFactory

        return lambda _profile, _strict_sync=False: NullPlayerFactory()

    def build(profile, strict_sync: bool = False):
        if strict_sync:
            from cctv_wall.gst_sync import GStreamerSyncPlayerFactory

            return GStreamerSyncPlayerFactory()
        from cctv_wall.player import VlcPlayerFactory

        return VlcPlayerFactory(profile)

    return build


def _check(bundled: Path | None) -> int:
    """Report what this build can actually reach. For diagnosing a deployed exe."""
    lines = [f"config file : {default_config_path()}",
             f"bundled VLC : {bundled or 'no (using the VLC installed on this PC)'}"]
    status = 0
    try:
        import vlc

        instance = vlc.Instance("--no-audio", "--no-video")
        if instance is None:
            raise OSError("libvlc found but it rejected the startup options")
        lines.append(f"libvlc      : {vlc.libvlc_get_version().decode(errors='replace')}")
        lines.append(f"library     : {vlc.plugin_path or 'bundled'}")
        instance.release()
    except (ImportError, OSError, AttributeError) as e:
        lines.append(f"libvlc      : UNAVAILABLE — {e}")
        lines.append(VLC_HINT)
        status = 2
    try:
        # Import exactly what resolvers.py needs, so a pass here really means YouTube works.
        from yt_dlp import YoutubeDL, version as yt_version  # noqa: F401

        lines.append(f"yt-dlp      : {yt_version.__version__}")
    except Exception as e:
        # A diagnostic must report rather than crash, and yt-dlp drags in a long tail of
        # optional dependencies — so name the actual failure instead of guessing at it.
        lines.append(f"yt-dlp      : UNAVAILABLE — {type(e).__name__}: {e}")
        lines.append("              only YouTube sources are affected; RTSP and files still work")
    try:
        # Build exactly what the sync button builds. The GI runtime loads inside this
        # constructor, so a pass here means pressing the button will really work.
        from cctv_wall.gst_sync import GStreamerSyncPlayerFactory

        factory = GStreamerSyncPlayerFactory()
        missing = factory.missing_elements()
        factory.shutdown()
        if missing:
            lines.append("strict sync : UNAVAILABLE — missing GStreamer elements: "
                         + ", ".join(missing))
            lines.append("              the wall still plays; only NTP timestamp sync is off")
        else:
            lines.append("strict sync : available")
    except Exception as e:
        # Same reasoning as yt-dlp: a diagnostic names the failure instead of crashing.
        lines.append(f"strict sync : UNAVAILABLE — {type(e).__name__}: {e}")
        lines.append("              the wall still plays; only NTP timestamp sync is off")
    message = "\n".join(lines)
    if sys.stdout is None:
        # Double-clicked windowed exe: no console exists, so show the report in a dialog.
        _show_report(message, failed=status != 0)
    else:
        print(message)
    return status


def _show_report(message: str, failed: bool) -> None:
    """Only shut down the QApplication when this report is the one that created it."""
    existing = QApplication.instance()
    application = existing or QApplication([])
    show = QMessageBox.critical if failed else QMessageBox.information
    show(None, "CCTV Wall — environment check", message)
    if existing is None:
        application.quit()


def _apply_system_theme(application: QApplication, scheme: Qt.ColorScheme | None = None) -> None:
    """Match the operating-system appearance without changing any playback behaviour."""
    chosen = scheme or application.styleHints().colorScheme()
    application.setStyleSheet(application_style(chosen == Qt.ColorScheme.Dark))


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    dry_run = "--dry-run" in arguments
    log_file = configure_log()
    logger().info("application starting; log=%s", log_file)
    bundled = configure_vlc()  # no-op unless this is a frozen exe carrying its own libvlc
    if "--check" in arguments:
        status = _check(bundled)
        return status

    if not dry_run:
        try:
            import vlc  # noqa: F401  — checked here so the failure message stays friendly
        except (ImportError, OSError) as e:
            print(f"libvlc is unavailable: {e}\n{VLC_HINT}", file=sys.stderr)
            return 2

    application = QApplication(sys.argv)
    # Point sizes respect Windows display scaling; the platform default is too small for a
    # wall viewed from a distance.  Keep this independent from the visual theme.
    interface_font = QFont(application.font())
    interface_font.setPointSize(11)
    application.setFont(interface_font)
    _apply_system_theme(application)
    application.styleHints().colorSchemeChanged.connect(
        lambda scheme: _apply_system_theme(application, scheme))
    # This widget takes over from the native PyInstaller splash.  It is deliberately
    # created before configuration is read, so slower disks still get visible feedback.
    startup = StartupProgress()
    startup.show_at_center()
    startup.set_progress(20, "正在讀取設定…")

    try:
        workspace = load_workspace()
    except WorkspaceError as e:
        startup.dismiss()
        print(f"{e}\n\nFix or delete {default_config_path()} and try again.", file=sys.stderr)
        return 1

    startup.set_progress(45, "正在準備播放環境…")
    startup.set_progress(65, "正在載入監看介面…")
    try:
        # These imports pull in VLC, yt-dlp and the complete widget tree.  Delaying
        # them until after StartupProgress is visible makes slow PCs acknowledge a
        # launch immediately rather than presenting an unresponsive desktop.
        from cctv_wall.resolvers import default_resolver
        from cctv_wall.ui.app import MainWindow

        startup.set_progress(80, "正在建立影像牆…")
        window = MainWindow(workspace, _factory_builder(dry_run), default_resolver(), save_workspace)
    except Exception as e:  # a failure here would leave a dead window: say why, then stop
        startup.dismiss()
        application.quit()
        print(f"could not start: {e}", file=sys.stderr)
        return 1

    startup.set_progress(100, "準備完成")
    if dry_run:
        window.show()
        application.processEvents()
        window.shutdown(persist=False)
        window.deleteLater()
        startup.dismiss()
        return 0
    window.show()
    startup.dismiss()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
