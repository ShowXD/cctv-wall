# PyInstaller build recipe. Use `uv run build cctv-wall` for a complete release.
# Direct spec invocation remains available for diagnostics. The release command always
# sets CCTV_WALL_ONEFILE=1, producing one self-contained executable.
#
# If VLC is found on this machine its libraries are copied in, so the result runs
# on a PC with no VLC installed. If not found, the exe is still built but the
# target PC needs VLC installed. The build prints which of the two happened.
#
# Override the VLC location with:  set CCTV_WALL_VLC_DIR=D:\some\vlc
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

APP_NAME = "CCTVWall"
PROJECT_ROOT = Path(SPECPATH)
BUNDLE_SUBDIRECTORY = "vlc"          # must match cctv_wall.vlc_runtime
GSTREAMER_SUBDIRECTORY = "gstreamer"  # must match cctv_wall.gst_sync
# gstreamer_libs' plugins already arrive with the runtime tree, and gtk4 sinks are
# useless to a Qt app that renders through d3d11videosink. Copying either again only
# inflates the exe: together they were ~93 MB of duplicate payload.
SKIPPED_PLUGIN_PACKAGES = frozenset({"gstreamer_libs", "gstreamer_gtk"})
LIBRARY_NAMES = ("libvlc.dll", "libvlccore.dll")
# VLC's plugin cache records absolute paths and timestamps from the build machine.
# Shipping it makes libvlc log a "stale plugins cache" error for every plugin and
# rescan anyway, so leave it out and let it build its own.
SKIPPED_PLUGIN_FILES = frozenset({"plugins.dat"})
CANDIDATE_VLC_DIRS = (
    r"C:\Program Files\VideoLAN\VLC",
    r"C:\Program Files (x86)\VideoLAN\VLC",
)
ONEFILE = os.environ.get("CCTV_WALL_ONEFILE", "").strip().lower() in {"1", "true", "yes"}


def discovered_vlc_dir():
    """Where python-vlc found VLC: it already searches the registry and PATH."""
    try:
        import vlc
    except (ImportError, OSError):
        return None
    return vlc.plugin_path or None


def find_vlc_dir():
    """The VLC install to bundle, or None to build an exe that needs VLC installed."""
    override = os.environ.get("CCTV_WALL_VLC_DIR", "").strip()
    if override:
        candidates = [override]
    else:
        candidates = [d for d in (discovered_vlc_dir(),) if d] + list(CANDIDATE_VLC_DIRS)
    for candidate in candidates:
        directory = Path(candidate)
        if all((directory / name).exists() for name in LIBRARY_NAMES):
            return directory
    return None


def vlc_payload(directory):
    """(binaries, datas) placing libvlc and its plugins under vlc/ inside the bundle."""
    if directory is None:
        return [], []
    binaries = [(str(directory / name), BUNDLE_SUBDIRECTORY) for name in LIBRARY_NAMES]
    plugins_root = directory / "plugins"
    if not plugins_root.is_dir():
        return binaries, []
    # Plugins are DLLs, so they belong in binaries: PyInstaller then fixes up their
    # dependencies instead of copying them as opaque data.
    for path in plugins_root.rglob("*"):
        if not path.is_file() or path.name in SKIPPED_PLUGIN_FILES:
            continue
        destination = Path(BUNDLE_SUBDIRECTORY) / "plugins" / path.parent.relative_to(
            plugins_root)
        binaries.append((str(path), str(destination)))
    return binaries, []


def gstreamer_payload():
    """Bundle the optional PyPI GStreamer runtime when the build environment has it.

    The sync backend loads GStreamer through its Python GI bindings, which PyInstaller
    cannot discover automatically. Keep each wheel's plugin directory separate so plugin
    wheels cannot overwrite each other, then let gst_sync publish all of them at runtime.
    """
    site_packages = next((Path(entry) for entry in sys.path
                          if (Path(entry) / "gstreamer_libs" / "bin").is_dir()), None)
    if site_packages is None:
        return [], []
    binaries, datas = [], []

    def include_tree(source, destination):
        """Preserve a wheel's layout; GStreamer also needs non-DLL support files."""
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            target = Path(destination) / path.parent.relative_to(source)
            # DLLs/PYD files must be classified as binaries for dependency collection.
            (binaries if path.suffix.lower() in {".dll", ".pyd"} else datas).append(
                (str(path), str(target)))

    runtime_root = site_packages / "gstreamer_libs"
    # lib/girepository-1.0, libexec/gst-plugin-scanner and share/ are all required
    # at runtime. Copying only bin/*.dll lets GI import but makes Gst unavailable.
    include_tree(runtime_root, f"{GSTREAMER_SUBDIRECTORY}/runtime")
    # The wheel split keeps Microsoft CRT companions in a separate package.
    ext_runtime = site_packages / "gstreamer_ext_runtime" / "bin"
    if ext_runtime.is_dir():
        include_tree(ext_runtime, f"{GSTREAMER_SUBDIRECTORY}/runtime/bin")
    for package in site_packages.glob("gstreamer_*"):
        # Plugin wheels can have a companion bin/ directory.  In particular,
        # gstlibav.dll needs FFmpeg's avcodec/avutil DLLs from
        # gstreamer_plugins_libs/bin.  Leaving them out works on machines whose
        # GPU exposes d3d11h264dec, but leaves older Windows drivers with no H.264
        # decoder at all.  Put every plugin support DLL beside the runtime so
        # GLib can load a software decoder as a reliable fallback.
        support_binaries = package / "bin"
        if package.name not in {"gstreamer_libs", "gstreamer_ext_runtime"} and support_binaries.is_dir():
            include_tree(support_binaries, f"{GSTREAMER_SUBDIRECTORY}/runtime/bin")
        if package.name in SKIPPED_PLUGIN_PACKAGES:
            continue
        plugins = package / "lib" / "gstreamer-1.0"
        if not plugins.is_dir():
            continue
        destination = Path(GSTREAMER_SUBDIRECTORY) / "plugins" / package.name
        include_tree(plugins, destination)
    # gstreamer-bundle places PyGObject in a private site-packages directory. It is
    # loaded dynamically by gst_sync, so include it explicitly with its typelibs.
    python_root = site_packages / "gstreamer_python"
    if python_root.is_dir():
        bundle_root = Path(GSTREAMER_SUBDIRECTORY) / "python"
        include_tree(python_root, bundle_root)
    return binaries, datas


vlc_dir = find_vlc_dir()
vlc_binaries, vlc_datas = vlc_payload(vlc_dir)
gstreamer_binaries, gstreamer_datas = gstreamer_payload()
if ONEFILE and not gstreamer_binaries:
    raise SystemExit(
        "strict timestamp sync runtime is missing; run `uv sync` before `uv run build cctv-wall`")
print("[cctv-wall] VLC bundling: "
      + (f"{len(vlc_binaries)} files from {vlc_dir}" if vlc_dir
         else "DISABLED — target PC must install VLC"), file=sys.stderr)
print(f"[cctv-wall] output mode : {'onefile' if ONEFILE else 'onedir (direct spec only)'}",
      file=sys.stderr)
print("[cctv-wall] GStreamer strict-sync bundling: "
      + (f"{len(gstreamer_binaries)} files" if gstreamer_binaries else "DISABLED"),
      file=sys.stderr)

# yt-dlp imports its extractors lazily; collect_all keeps them reachable.
yt_datas, yt_binaries, yt_hiddenimports = collect_all("yt_dlp")

analysis = Analysis(
    [str(PROJECT_ROOT / "src" / "cctv_wall" / "__main__.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=vlc_binaries + gstreamer_binaries + yt_binaries,
    datas=vlc_datas + gstreamer_datas + yt_datas,
    hiddenimports=["vlc"] + yt_hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Nothing here draws plots or crunches arrays; excluding these keeps the build small.
    # `gi` is copied as data next to its matching GStreamer DLLs below. Letting
    # PyInstaller's GI hook add a second copy at the bundle root makes Python import
    # the wrong one first, which prevents strict timestamp sync from starting.
    excludes=[
        "numpy", "matplotlib", "PIL", "pytest", "setuptools", "pip",
        "gi", "gi.repository", "gstreamer_bundle", "gstreamer_libs", "gstreamer_python",
    ],
    noarchive=False,
)

def _is_unreachable_gstreamer_copy(entry):
    """True for the bundle-root copy of a gstreamer wheel, which nothing can load.

    The gstreamer-bundle wheels add themselves to sys.path at build time (see
    gstreamer_bundle.pth), so PyInstaller's scanner collects a second copy of every DLL
    under `<wheel_name>/...` at the bundle root. Nothing reaches those: gst_sync points
    GI, the plugin scanner and PATH at the `gstreamer/` tree above, and the root copies
    sit in directories that are on no search path. `excludes` cannot drop them because
    they arrive as collected binaries rather than as imported modules.
    """
    top = str(entry[0]).replace("\\", "/").split("/")[0]
    return top.startswith("gstreamer_")


_before = len(analysis.binaries) + len(analysis.datas)
analysis.binaries = [e for e in analysis.binaries if not _is_unreachable_gstreamer_copy(e)]
analysis.datas = [e for e in analysis.datas if not _is_unreachable_gstreamer_copy(e)]
print(f"[cctv-wall] dropped {_before - len(analysis.binaries) - len(analysis.datas)}"
      " duplicate GStreamer files from the bundle root", file=sys.stderr)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries if ONEFILE else [],
    analysis.datas if ONEFILE else [],
    name=APP_NAME,
    console=False,          # a GUI app: no console window on Windows
    debug=False,
    strip=False,
    upx=False,              # UPX is known to corrupt VLC plugin DLLs
    onefile=ONEFILE,
    icon=None,
    bootloader_ignore_signals=False,
    disable_windowed_traceback=False,
    exclude_binaries=not ONEFILE,
)

if not ONEFILE:
    COLLECT(exe, analysis.binaries, analysis.datas, name=APP_NAME,
            strip=False, upx=False)
