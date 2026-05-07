from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lufus.drives import get_usb_info as get_usb_info_module


# ---------------------------------------------------------------------------
# Shared pyudev mock helpers
# ---------------------------------------------------------------------------


def _make_fake_stat(rdev=0x803):
    return SimpleNamespace(st_rdev=rdev)


def _make_fake_device(size_sectors=None, label=""):
    """Return a minimal pyudev device stub."""

    class FakeAttributes:
        def get(self, key, default=None):
            if key == "size":
                return str(size_sectors) if size_sectors is not None else None
            return default

    class FakeDevice:
        attributes = FakeAttributes()

        def get(self, key, default=None):
            if key == "ID_FS_LABEL":
                return label or None
            return default

    return FakeDevice()


def _patch_pyudev(monkeypatch, device_stub):
    """Patch pyudev.Context and pyudev.Devices.from_device_number."""
    monkeypatch.setattr(get_usb_info_module.pyudev, "Context", lambda: SimpleNamespace())
    monkeypatch.setattr(
        get_usb_info_module.pyudev.Devices,
        "from_device_number",
        lambda ctx, kind, rdev: device_stub,
    )
    monkeypatch.setattr(
        get_usb_info_module.os,
        "stat",
        lambda path: _make_fake_stat(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_usb_info_returns_empty_when_mount_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        get_usb_info_module.psutil,
        "disk_partitions",
        lambda *args, **kwargs: [SimpleNamespace(mountpoint="/mnt/other", device="/dev/sdb1")],
    )

    assert get_usb_info_module.get_usb_info("/media/testuser/USB") is None


def test_get_usb_info_returns_expected_dictionary(monkeypatch) -> None:
    mount_path = "/media/testuser/USB"
    device_node = "/dev/sdb1"

    monkeypatch.setattr(
        get_usb_info_module.psutil,
        "disk_partitions",
        lambda *args, **kwargs: [SimpleNamespace(mountpoint=mount_path, device=device_node)],
    )
    _patch_pyudev(monkeypatch, _make_fake_device(size_sectors=16 * 1024**3 // 512, label="MYUSB"))

    result = get_usb_info_module.get_usb_info(mount_path)
    assert result == {
        "device_node": device_node,
        "label": "MYUSB",
        "mount_path": mount_path,
    }


def test_get_usb_info_uses_mount_basename_when_label_is_empty(monkeypatch) -> None:
    mount_path = "/media/testuser/NO_LABEL"
    device_node = "/dev/sdc1"

    monkeypatch.setattr(
        get_usb_info_module.psutil,
        "disk_partitions",
        lambda *args, **kwargs: [SimpleNamespace(mountpoint=mount_path, device=device_node)],
    )
    _patch_pyudev(monkeypatch, _make_fake_device(size_sectors=8 * 1024**3 // 512, label=""))

    result = get_usb_info_module.get_usb_info(mount_path)
    assert result["label"] == "NO_LABEL"


def test_get_usb_info_returns_empty_when_pyudev_fails(monkeypatch) -> None:
    """get_usb_info must return None when pyudev.Devices.from_device_number raises."""
    mount_path = "/media/testuser/USB"
    device_node = "/dev/sdb1"

    monkeypatch.setattr(
        get_usb_info_module.psutil,
        "disk_partitions",
        lambda *args, **kwargs: [SimpleNamespace(mountpoint=mount_path, device=device_node)],
    )
    monkeypatch.setattr(
        get_usb_info_module.os,
        "stat",
        lambda path: _make_fake_stat(),
    )
    monkeypatch.setattr(get_usb_info_module.pyudev, "Context", lambda: SimpleNamespace())

    def failing_from_device_number(context, device_type, device_number):
        raise RuntimeError("pyudev failure in from_device_number")

    monkeypatch.setattr(
        get_usb_info_module.pyudev.Devices,
        "from_device_number",
        failing_from_device_number,
    )

    result = get_usb_info_module.get_usb_info(mount_path)
    assert result is None
