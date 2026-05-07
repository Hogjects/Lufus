"""Regression tests for bugs fixed in flash_usb.py and find_usb.py.

Each test is named after the bug it reproduces and verifies the fix.
Tests use monkeypatching so no real hardware, dd, or network is needed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import lufus.writing.flash_usb as flash_usb_module
from lufus.utils import strip_partition_suffix
from lufus.writing.flash_usb import flash_usb
import lufus.drives.find_usb as find_usb_module
from lufus.drives.find_usb import _media_directories


# ---------------------------------------------------------------------------
# strip_partition_suffix — BUG: re.sub(r"[0-9]+$") mangled NVMe names
# ---------------------------------------------------------------------------


class TestStripPartitionSuffix:
    """Before the fix, `re.sub(r'[0-9]+$', '', '/dev/nvme0n1p1')` produced
    '/dev/nvme0n' — stripping the trailing '1' of the namespace component.
    The new helper must handle NVMe, MMC, and standard SCSI correctly.
    """

    def test_nvme_partition_stripped_correctly(self):
        # BUG: old code gave '/dev/nvme0n' (stripped '1' from 'n1')
        assert strip_partition_suffix("/dev/nvme0n1p1") == "/dev/nvme0n1"

    def test_nvme_multi_digit_namespace_and_partition(self):
        assert strip_partition_suffix("/dev/nvme1n2p3") == "/dev/nvme1n2"

    def test_mmc_partition_stripped_correctly(self):
        assert strip_partition_suffix("/dev/mmcblk0p1") == "/dev/mmcblk0"

    def test_mmc_multi_digit_partition(self):
        assert strip_partition_suffix("/dev/mmcblk1p12") == "/dev/mmcblk1"

    def test_scsi_single_digit_partition(self):
        assert strip_partition_suffix("/dev/sdb1") == "/dev/sdb"

    def test_scsi_multi_digit_partition(self):
        assert strip_partition_suffix("/dev/sda10") == "/dev/sda"

    def test_whole_disk_unchanged(self):
        assert strip_partition_suffix("/dev/sdb") == "/dev/sdb"

    def test_nvme_whole_disk_unchanged(self):
        assert strip_partition_suffix("/dev/nvme0n1") == "/dev/nvme0n1"

    def test_unknown_path_unchanged(self):
        assert strip_partition_suffix("/dev/loop0") == "/dev/loop0"


# ---------------------------------------------------------------------------
# flash_usb — BUG: OSError from os.path.getsize propagated instead of False
# ---------------------------------------------------------------------------


class Testflash_usbOsError:
    """Before the fix, calling flash_usb with a non-existent iso_path raised
    OSError (from os.path.getsize). Callers expect a bool return value.
    """

    def test_returns_false_when_iso_path_does_not_exist(self, tmp_path):
        missing = str(tmp_path / "nonexistent.iso")
        result = flash_usb("/dev/sdb", missing)
        assert result is False

    def test_returns_false_when_iso_path_is_directory(self, tmp_path):
        result = flash_usb("/dev/sdb", str(tmp_path))
        assert result is False


# ---------------------------------------------------------------------------
# flash_usb — BUG: FileNotFoundError from Popen propagated instead of False
# ---------------------------------------------------------------------------


class Testflash_usbDdNotFound:
    """Before the fix, if dd was absent, Popen raised FileNotFoundError
    which was not caught — the caller received an exception instead of False.
    """

    def test_returns_false_when_dd_not_found(self, tmp_path, monkeypatch):
        iso = tmp_path / "valid.iso"
        # Write a minimal valid ISO9660 PVD so signature check passes
        payload = bytearray(32775)
        payload[32768] = 0x01
        payload[32769:32774] = b"CD001"
        payload[32774] = 0x01
        iso.write_bytes(bytes(payload))

        # Patch is_windows_iso to avoid 7z subprocess
        monkeypatch.setattr(flash_usb_module, "is_windows_iso", lambda p: False)
        # Patch check_iso_signature to pass
        monkeypatch.setattr(flash_usb_module, "check_iso_signature", lambda p: True)

        # Make Popen raise FileNotFoundError (dd absent)
        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError("dd not found")

        monkeypatch.setattr(flash_usb_module.subprocess, "Popen", raise_fnf)

        result = flash_usb("/dev/sdb", str(iso))
        assert result is False


# ---------------------------------------------------------------------------
# flash_usb — device stripping uses correct helper (NVMe regression guard)
# ---------------------------------------------------------------------------


class Testflash_usbNvmeDeviceStrip:
    """Ensure flash_usb forwards the correctly stripped NVMe device to dd."""

    def test_nvme_device_stripped_before_dd(self, tmp_path, monkeypatch):
        iso = tmp_path / "test.img"
        iso.write_bytes(b"\x00" * 100)

        monkeypatch.setattr(flash_usb_module, "check_iso_signature", lambda p: True)
        monkeypatch.setattr(flash_usb_module, "is_windows_iso", lambda p: False)

        popen_calls = {}

        class FakeProcess:
            pid = 12345
            returncode = 0

            def __init__(self, args, **kwargs):
                popen_calls["args"] = args
                self.stderr = FakePipe()

            def wait(self):
                pass

        class FakePipe:
            def __iter__(self):
                return iter([])

            def read1(self, size=-1):
                return b""

        monkeypatch.setattr(flash_usb_module.subprocess, "Popen", FakeProcess)

        flash_usb("/dev/nvme0n1p1", str(iso))

        dd_of = next((a for a in popen_calls["args"] if a.startswith("of=")), None)
        assert dd_of == "of=/dev/nvme0n1", f"Expected of=/dev/nvme0n1, got {dd_of}"


# ---------------------------------------------------------------------------
# find_usb / find_device_node — BUG: duplicated path-scan logic (DRY violation)
# ---------------------------------------------------------------------------


class TestMediaDirectories:
    """_media_directories() must deduplicate entries — before the fix
    the two scan passes could yield duplicate entries for the same path.
    """

    def test_no_duplicates_in_result(self, monkeypatch):
        user = "testuser"
        monkeypatch.setattr(find_usb_module.getpass, "getuser", lambda: user)

        # /media contains 'testuser' (a dir), /media/testuser also exists
        # — the old code would add /media/testuser/USB twice.
        def fake_exists(p):
            return p in {"/media", f"/media/{user}", f"/media/{user}/USB"}

        def fake_isdir(p):
            return fake_exists(p)

        def fake_listdir(p):
            if p == "/media":
                return [user]  # yields /media/testuser
            if p == f"/media/{user}":
                return ["USB"]  # yields /media/testuser/USB
            return []

        monkeypatch.setattr(find_usb_module.os.path, "exists", fake_exists)
        monkeypatch.setattr(find_usb_module.os.path, "isdir", fake_isdir)
        monkeypatch.setattr(find_usb_module.os, "listdir", fake_listdir)

        result = _media_directories()
        # No duplicates
        assert len(result) == len(set(result)), f"Duplicates found: {result}"


# ---------------------------------------------------------------------------
# find_usb — BUG: psutil.disk_partitions() called without all=True
# ---------------------------------------------------------------------------


class TestFindUsbUsesAllPartitions:
    """find_usb must call disk_partitions(all=True) so bind-mounted USB
    volumes are not silently skipped on systems that use them.
    """

    def test_find_usb_passes_all_true_to_disk_partitions(self, monkeypatch):
        calls = {}

        def fake_disk_partitions(all=False):
            calls["all"] = all
            return []

        monkeypatch.setattr(find_usb_module.psutil, "disk_partitions", fake_disk_partitions)
        monkeypatch.setattr(find_usb_module.getpass, "getuser", lambda: "u")
        monkeypatch.setattr(find_usb_module.os.path, "exists", lambda p: False)
        monkeypatch.setattr(find_usb_module.os.path, "isdir", lambda p: False)

        find_usb_module.find_usb()
        assert calls.get("all") is True

    def test_find_dn_passes_all_true_to_disk_partitions(self, monkeypatch):
        calls = {}

        def fake_disk_partitions(all=False):
            calls["all"] = all
            return []

        monkeypatch.setattr(find_usb_module.psutil, "disk_partitions", fake_disk_partitions)
        monkeypatch.setattr(find_usb_module.getpass, "getuser", lambda: "u")
        monkeypatch.setattr(find_usb_module.os.path, "exists", lambda p: False)
        monkeypatch.setattr(find_usb_module.os.path, "isdir", lambda p: False)

        find_usb_module.find_device_node()
        assert calls.get("all") is True


# ---------------------------------------------------------------------------
# find_device_node — BUG: empty device_node would overwrite states.DN with ""
# ---------------------------------------------------------------------------


class TestFindDNGuardsEmptyDevice:
    """find_device_node must not write an empty string to states.DN."""

    def test_empty_device_node_does_not_overwrite_states_dn(self, monkeypatch):
        from lufus import state as state_mod

        user = "testuser"
        mount_path = f"/media/{user}/USB"
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
            lambda p: ["USB"] if p == f"/media/{user}" else [],
        )
        # Partition with empty device string
        monkeypatch.setattr(
            find_usb_module.psutil,
            "disk_partitions",
            lambda *args, **kwargs: [SimpleNamespace(mountpoint=mount_path, device="")],
        )

        state_mod.device_node = "/dev/sdb1"  # set a valid value first
        result = find_usb_module.find_device_node()

        assert result is None, "find_device_node should return None when device is empty"
        assert state_mod.device_node == "/dev/sdb1", "states.DN must not be overwritten with empty string"


# ---------------------------------------------------------------------------
# Existing-behaviour smoke tests (ensure refactor didn't break happy paths)
# ---------------------------------------------------------------------------


class TestFindUsbHappyPath:
    def test_find_usb_returns_label_from_udev(self, monkeypatch):
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

        from types import SimpleNamespace as SNS

        class FakeDevice:
            def get(self, key, default=None):
                return "MY_LABEL" if key == "ID_FS_LABEL" else default

        monkeypatch.setattr(find_usb_module.pyudev, "Context", lambda: SNS())
        monkeypatch.setattr(find_usb_module.os, "stat", lambda path: SNS(st_rdev=0x803))
        monkeypatch.setattr(
            find_usb_module.pyudev.Devices,
            "from_device_number",
            lambda ctx, kind, rdev: FakeDevice(),
        )

        result = find_usb_module.find_usb()
        assert result == {mount_path: "MY_LABEL"}

    def test_find_dn_returns_device_node(self, monkeypatch):
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


# ---------------------------------------------------------------------------
# flash_usb — progress reporting, LC_ALL env, and stderr line filtering
# ---------------------------------------------------------------------------


class TestFlashUsbProgress:
    """Verify progress_cb milestones, dd stderr parsing, LC_ALL handling, and
    filtering of bookkeeping lines vs. unexpected stderr warnings.
    """

    def _fake_popen_factory(self, stderr_lines, popen_calls, envs):
        class FakePopen:
            class FakeStderr:
                def __init__(self, lines):
                    self._lines = [line.encode("utf-8") for line in lines]
                    self._index = 0

                def read1(self, size=-1):
                    if self._index >= len(self._lines):
                        return b""
                    result = self._lines[self._index]
                    self._index += 1
                    return result

            def __init__(self, cmd, **kwargs):
                popen_calls.append((cmd, kwargs))
                envs.append(kwargs.get("env"))
                self.pid = 99999
                self.returncode = 0
                self.stderr = FakePopen.FakeStderr(stderr_lines)

            def wait(self):
                return self.returncode

        return FakePopen

    def test_progress_cb_receives_milestones_and_scaled_dd_progress(self, monkeypatch):
        progress_values = []
        status_messages = []

        def progress_cb(progress):
            progress_values.append(progress)

        def status_cb(message):
            status_messages.append(message)

        stderr_lines = [
            "0+0 records in\n",
            "0+0 records out\n",
            "10% completed\n",
            "12345+0 records in\n",
            "12345+0 records out\n",
            "50% completed\n",
            "copied, 1.23 s, 4.56 MB/s\n",
            "100% completed\n",
        ]

        popen_calls = []
        envs = []
        fake_popen = self._fake_popen_factory(stderr_lines, popen_calls, envs)
        monkeypatch.setattr(flash_usb_module.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(flash_usb_module, "check_iso_signature", lambda p: True)
        monkeypatch.setattr(flash_usb_module, "is_windows_iso", lambda p: False)
        monkeypatch.setattr(flash_usb_module, "detect_iso_type", lambda p: flash_usb_module.IsoType.LINUX)

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as f:
            f.write(b"\x00" * 100)
            iso_path = f.name

        original_environ = dict(os.environ)
        try:
            flash_usb_module.flash_usb("/dev/sdb", iso_path, progress_cb=progress_cb, status_cb=status_cb)
        finally:
            os.unlink(iso_path)

        # LC_ALL must be "C" and global env must not be mutated
        dd_call = next((c for c in popen_calls if c[0] and c[0][0] == "dd"), None)
        assert dd_call is not None, "dd Popen should have been called"
        env = dd_call[1].get("env")
        assert env is not None
        assert env.get("LC_ALL") == "C"
        assert dict(os.environ) == original_environ

        # progress_cb should have the early 0 milestone, then scaled values
        assert progress_values[0] == 0
        assert progress_values[-1] == 100
        assert sorted(progress_values) == progress_values

        # Status messages should contain the raw dd progress lines
        assert any("10% completed" in msg for msg in status_messages)
        assert any("50% completed" in msg for msg in status_messages)
        assert any("100% completed" in msg for msg in status_messages)

    def test_non_progress_and_unexpected_stderr_lines_handling(self, monkeypatch, caplog):
        progress_values = []
        status_messages = []

        def progress_cb(progress):
            progress_values.append(progress)

        def status_cb(message):
            status_messages.append(message)

        stderr_lines = [
            "1+0 records in\n",
            "1+0 records out\n",
            "copied, 1.23 s, 4.56 MB/s\n",
            "some unexpected warning from dd\n",
        ]

        popen_calls = []
        envs = []
        fake_popen = self._fake_popen_factory(stderr_lines, popen_calls, envs)
        monkeypatch.setattr(flash_usb_module.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(flash_usb_module, "check_iso_signature", lambda p: True)
        monkeypatch.setattr(flash_usb_module, "is_windows_iso", lambda p: False)
        monkeypatch.setattr(flash_usb_module, "detect_iso_type", lambda p: flash_usb_module.IsoType.LINUX)

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as f:
            f.write(b"\x00" * 100)
            iso_path = f.name

        with caplog.at_level("INFO", logger="lufus"):
            try:
                flash_usb_module.flash_usb("/dev/sdb", iso_path, progress_cb=progress_cb, status_cb=status_cb)
            finally:
                os.unlink(iso_path)

        # Only the initial 0 milestone should be present;
        # bookkeeping lines must not trigger additional progress_cb calls
        assert progress_values == [0]

        # Non-progress stderr lines now log at info level
        unexpected_logs = [
            record for record in caplog.records if "some unexpected warning from dd" in record.getMessage()
        ]
        assert unexpected_logs, "Unexpected stderr lines should produce an info log entry"
