from __future__ import annotations
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lufus.writing.windows.detect import is_linux_iso


def test_is_linux_iso_detects_marker(monkeypatch):
    mock_run = MagicMock()
    mock_run.return_value = subprocess.CompletedProcess(
        args=["7z", "l", "test.iso"], returncode=0, stdout="isolinux/isolinux.cfg\nvmlinuz\ninitrd.img", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert is_linux_iso("test.iso") is True


def test_is_linux_iso_fails_without_marker(monkeypatch):
    mock_run = MagicMock()
    mock_run.return_value = subprocess.CompletedProcess(
        args=["7z", "l", "test.iso"], returncode=0, stdout="random/file/not/linux.txt", stderr=""
    )
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert is_linux_iso("test.iso") is False
