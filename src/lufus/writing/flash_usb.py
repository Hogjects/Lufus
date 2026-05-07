import os
import re
import shlex
import subprocess
from lufus.utils import strip_partition_suffix
from lufus.writing.check_file_sig import check_iso_signature
from lufus.writing.windows.detect import detect_iso_type, IsoType, is_windows_iso
from lufus.writing.windows.flash import flash_windows
from lufus.lufus_logging import get_logger
from lufus.writing.partition_scheme import PartitionScheme

log = get_logger(__name__)


# TODO: Decide if these are needed — currently never called in this module
# def pkexec_not_found():
#     log.error("The command pkexec or labeling software was not found on your system.")
#
# def format_fail():
#     log.error("Formatting failed. Was the password correct? Is the drive unmounted?")
#
# def log_unexpected_error():
#     log.error("An unexpected error occurred")


def flash_usb(
    device: str, iso_path: str, scheme: PartitionScheme = PartitionScheme.SIMPLE_FAT32, progress_cb=None, status_cb=None
) -> bool:
    def _status(msg: str) -> None:
        log.info(msg)
        if status_cb:
            status_cb(msg)

    _status(f"flash_usb called: iso={iso_path}, device={device}")

    # Strip any partition suffix first (e.g. /dev/nvme0n1p1 -> /dev/nvme0n1,
    # /dev/sdb1 -> /dev/sdb) so that validation operates on the whole-disk path.
    original_device = device
    device = strip_partition_suffix(device)
    if device != original_device:
        _status(f"Stripped partition suffix: {original_device} -> {device}")

    # Validate the (already-stripped) device path before any operation —
    # prevents accidental writes to system disks if a bad options file or
    # UI bug passes a wrong path.
    if not re.match(r"^/dev/(sd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+)$", device):
        log.error("flash_usb: invalid device path %r — aborting", device)
        _status(f"Flash aborted: invalid device path {device!r}")
        return False

    try:
        iso_size = os.path.getsize(iso_path)
        _status(f"File size: {iso_size:,} bytes ({iso_size / (1024**3):.2f} GiB)")

        if iso_path.lower().endswith(".iso"):
            _status(f"Validating ISO9660 signature for: {iso_path}")
            if not check_iso_signature(iso_path):
                log.error("ISO signature check FAILED for %s, aborting flash", iso_path)
                _status(f"ISO signature check FAILED for {iso_path}, aborting flash")
                return False
            _status("ISO signature check passed")
        else:
            _status(f"Not an ISO file ({os.path.basename(iso_path)}), skipping ISO signature check")

        _status("Checking if image contains installation markers...")
        if is_windows_iso(iso_path):
            _status("Windows Installation media detected, routing to flash_windows (ISO mode)")
            return flash_windows(
                device,
                iso_path,
                scheme,
                progress_cb=progress_cb,
                status_cb=status_cb,
            )

        iso_type = detect_iso_type(iso_path)
        if iso_type == IsoType.LINUX:
            _status("Linux Installation media detected, will use dd for flashing")
        else:
            _status("Generic or unknown image, will use dd for flashing")

        dd_args = [
            "dd",
            f"if={iso_path}",
            f"of={device}",
            "bs=4M",
            "status=progress",
            "conv=fsync",
            "oflag=direct",
        ]

        _status(f"Spawning dd: {' '.join(dd_args)}")
        _status(f"Writing {iso_size:,} bytes to {shlex.quote(device)}, this may take several minutes...")

        # Build the environment with LC_ALL=C so dd's byte-count output uses the
        # predictable decimal format regardless of the system locale.  Copy
        # os.environ rather than mutating it so the global environment is unchanged.
        env = {**os.environ, "LC_ALL": "C"}

        # dd_args is constructed from a validated device path (regex-checked above)
        # and a user-supplied iso_path.  The list form of Popen (not shell=True)
        # means each element is passed directly to execve, so there is no shell
        # injection risk here.
        try:
            process = subprocess.Popen(dd_args, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, env=env)
        except FileNotFoundError:
            log.error("Flash failed: 'dd' utility not found. Install coreutils.")
            _status("Flash failed: 'dd' utility not found. Install coreutils.")
            return False

        _status(f"dd process started with PID {process.pid}")

        _status("Flash starting...")
        if progress_cb:
            progress_cb(0)

        # dd status=progress writes updates separated by \r (carriage return),
        # not \n.  Reading line-by-line from process.stderr blocks until a \n
        # is seen, so progress updates would only arrive at the very end.
        # read1() returns whatever bytes are currently in the pipe buffer
        # without waiting for a newline, letting us process \r-terminated
        # progress lines in real time.
        buf = b""
        while True:
            chunk = process.stderr.read1(65536)
            if not chunk:
                # Flush any remaining partial stderr fragment so it is not lost
                if buf:
                    decoded = buf.decode(errors="replace").rstrip("\r\n")
                    if decoded:
                        # Log at info to avoid alarming users with benign dd output
                        log.info("dd stderr (final fragment): %s", decoded)
                break
            buf += chunk
            segments = re.split(rb"[\r\n]", buf)
            # keep the last (possibly incomplete) segment for the next iteration
            buf = segments[-1]
            for segment_bytes in segments[:-1]:
                line_str = segment_bytes.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                # Percentage progress line (e.g. "50% completed" generated from
                # dd byte output, or pv-style "50%")
                pct_match = re.search(r"(\d+)%", line_str)
                if pct_match and iso_size > 0:
                    pct_int = min(int(pct_match.group(1)), 100)
                    _status(line_str)
                    if progress_cb:
                        progress_cb(pct_int)
                elif re.match(r"^\d+\s+bytes", line_str) and iso_size > 0:
                    # dd status=progress byte-count line
                    m = re.match(r"^(\d+)", line_str)
                    bytes_done = int(m.group(1))
                    pct_int = min(int(bytes_done * 100 / iso_size), 99)
                    status_str = f"{bytes_done:,} / {iso_size:,} bytes ({pct_int}% completed)"
                    _status(status_str)
                    if progress_cb:
                        progress_cb(pct_int)
                elif re.search(r"\brecords (in|out)\b", line_str) or re.search(r"\bcopied\b", line_str):
                    # dd bookkeeping lines — informational only, not progress events
                    pass
                else:
                    log.info("dd stderr: %s", line_str)

        process.wait()
        _status(f"dd process exited with return code {process.returncode}")

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, dd_args)

        _status(f"dd completed successfully: {iso_path} -> {device}")
        return True

    except OSError as e:
        log.error("Flash failed with OSError: %s", e)
        _status(f"Flash failed with OSError: {e}")
        return False
    except subprocess.CalledProcessError as e:
        log.error(
            "Flash failed with CalledProcessError: returncode=%d, cmd=%s",
            e.returncode,
            e.cmd,
        )
        _status(f"Flash failed with CalledProcessError: returncode={e.returncode}, cmd={e.cmd}")
        return False
