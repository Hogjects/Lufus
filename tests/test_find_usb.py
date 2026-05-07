from __future__ import annotations
import os as _real_os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lufus.drives import find_usb as find_usb_module


# ---------------------------------------------------------------------------
# Shared pyudev mock helpers
# ---------------------------------------------------------------------------

_ORIG_STAT = _real_os.stat


def _dev_stat(*args, **kwargs):
    """Return a fake stat result for /dev/* paths, pass through for everything else."""
    path = args[0] if args else kwargs.get("path", "")
    if str(path).startswith("/dev/"):
        return SimpleNamespace(st_rdev=0x803, st_size=0, st_mtime=0.0, st_mode=0o660)
    return _ORIG_STAT(*args, **kwargs)


def _dev_stat_raising(*args, **kwargs):
    """Raise PermissionError for /dev/* paths, pass through for everything else."""
    path = args[0] if args else kwargs.get("path", "")
    if str(path).startswith("/dev/"):
        raise PermissionError("no access to device")
    return _ORIG_STAT(*args, **kwargs)


def _patch_pyudev_label(monkeypatch, label):
    """Patch pyudev so find_usb resolves the given label without real udev."""

    class FakeDevice:
        def get(self, key, default=None):
            return label if key == "ID_FS_LABEL" else default

    monkeypatch.setattr(find_usb_module.pyudev, "Context", lambda: SimpleNamespace())
    monkeypatch.setattr(find_usb_module.os, "stat", _dev_stat)
    monkeypatch.setattr(
        find_usb_module.pyudev.Devices,
        "from_device_number",
        lambda ctx, kind, rdev: FakeDevice(),
    )


def _patch_pyudev_failing(monkeypatch):
    """Patch os.stat to fail for device nodes, exercising the label fallback path."""
    monkeypatch.setattr(find_usb_module.pyudev, "Context", lambda: SimpleNamespace())
    monkeypatch.setattr(find_usb_module.os, "stat", _dev_stat_raising)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_find_usb_returns_mount_to_label_mapping(monkeypatch) -> None:
    user = "testuser"
    mount_path = f"/media/{user}/MY_USB"

    monkeypatch.setattr(find_usb_module.getpass, "getuser", lambda: user)
    monkeypatch.setattr(
        find_usb_module.os.path,
        "exists",
        lambda p: p in {"/media", f"/media/{user}", mount_path},
    )
    monkeypatch.setattr(
        find_usb_module.os.path,
        "isdir",
        lambda p: p in {"/media", f"/media/{user}", mount_path},
    )
    monkeypatch.setattr(
        find_usb_module.os,
        "listdir",
        lambda p: ["MY_USB"] if p == f"/media/{user}" else [],
    )
    monkeypatch.setattr(
        find_usb_module.psutil,
        "disk_partitions",
        lambda *args, **kwargs: [SimpleNamespace(mountpoint=mount_path, device="/dev/sdb1")],
    )
    _patch_pyudev_label(monkeypatch, "lufus_USB")

    result = find_usb_module.find_usb()
    assert result == {mount_path: "lufus_USB"}


def test_find_usb_falls_back_to_dir_name_when_udev_fails(monkeypatch) -> None:
    user = "testuser"
    mount_path = f"/media/{user}/NO_LABEL"

    monkeypatch.setattr(find_usb_module.getpass, "getuser", lambda: user)
    monkeypatch.setattr(
        find_usb_module.os.path,
        "exists",
        lambda p: p in {"/media", f"/media/{user}", mount_path},
    )
    monkeypatch.setattr(
        find_usb_module.os.path,
        "isdir",
        lambda p: p in {"/media", f"/media/{user}", mount_path},
    )
    monkeypatch.setattr(
        find_usb_module.os,
        "listdir",
        lambda p: ["NO_LABEL"] if p == f"/media/{user}" else [],
    )
    monkeypatch.setattr(
        find_usb_module.psutil,
        "disk_partitions",
        lambda *args, **kwargs: [SimpleNamespace(mountpoint=mount_path, device="/dev/sdc1")],
    )
    _patch_pyudev_failing(monkeypatch)

    result = find_usb_module.find_usb()
    assert result == {mount_path: "NO_LABEL"}


def test_find_dn_returns_matching_device_node(monkeypatch) -> None:
    user = "testuser"
    mount_path = f"/media/{user}/FLASH"

    monkeypatch.setattr(find_usb_module.getpass, "getuser", lambda: user)
    monkeypatch.setattr(
        find_usb_module.os.path,
        "exists",
        lambda p: p in {"/media", f"/media/{user}", mount_path},
    )
    monkeypatch.setattr(
        find_usb_module.os.path,
        "isdir",
        lambda p: p in {"/media", f"/media/{user}", mount_path},
    )
    monkeypatch.setattr(
        find_usb_module.os,
        "listdir",
        lambda p: ["FLASH"] if p == f"/media/{user}" else [],
    )
    monkeypatch.setattr(
        find_usb_module.psutil,
        "disk_partitions",
        lambda *args, **kwargs: [SimpleNamespace(mountpoint=mount_path, device="/dev/sdd1")],
    )

    assert find_usb_module.find_device_node() == "/dev/sdd1"
