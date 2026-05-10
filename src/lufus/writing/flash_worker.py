#!/usr/bin/env python3
import sys
import json
import os
import signal
import glob
from lufus.lufus_logging import get_logger, setup_logging
from lufus import state
from lufus.drives import formatting as fo
from lufus.writing.flash_usb import flash_usb

setup_logging()
log = get_logger(__name__)

# Start a new process group so all children can be killed together
os.setpgrp()

# Write PID to a root-owned directory so unprivileged users cannot create
# symlinks there before we open the file (TOCTOU prevention).
# Fall back to a process-specific /tmp name only if /run is unavailable.
_pid_dir = "/run/lufus"
try:
    os.makedirs(_pid_dir, mode=0o700, exist_ok=True)
    pid_file = os.path.join(_pid_dir, "helper.pid")
except OSError:
    # /run not writable (unusual); use a non-guessable name as best-effort
    pid_file = f"/tmp/lufus_helper_{os.getpid()}.pid"

# O_CREAT | O_TRUNC with mode 0o600 — safe because the directory is 0o700 root-owned
_fd = os.open(pid_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
try:
    os.write(_fd, str(os.getpid()).encode())
finally:
    os.close(_fd)

_ipc_msg = f"Helper started with PID={os.getpid()}, PGID={os.getpgrp()}"
print(f"STATUS:{_ipc_msg}")
sys.stdout.flush()
log.info(_ipc_msg)


def progress_cb(pct):
    print(f"PROGRESS:{pct}")
    sys.stdout.flush()
    log.debug("Progress: %s%%", pct)


def status_cb(msg):
    print(f"STATUS:{msg}")
    sys.stdout.flush()
    log.info("Status IPC: %s", msg)


def main():
    try:
        if len(sys.argv) != 2:
            _err = "Missing arguments"
            print(f"STATUS:{_err}")
            sys.stdout.flush()
            log.error(_err)
            sys.exit(1)

        options_file = sys.argv[1]
        try:
            with open(options_file, "r") as f:
                options = json.load(f)
        except Exception as e:
            _err = f"Failed to read options file: {e}"
            print(f"STATUS:{_err}")
            sys.stdout.flush()
            log.error(_err)
            sys.exit(1)

        # Clean up the temp file
        try:
            os.unlink(options_file)
        except Exception:
            pass

        # Set all states
        for key, value in options.items():
            if hasattr(state, key):
                setattr(state, key, value)

        device_node = options["device"]
        iso_path = options.get("iso_path", "")
        image_option = options["image_option"]

        # Unmount all partitions
        _msg = f"Unmounting all partitions on {device_node}..."
        print(f"STATUS:{_msg}")
        sys.stdout.flush()
        log.info(_msg)

        partitions = glob.glob(f"{device_node}*")
        for part in partitions:
            _pmsg = f"Unmounting {part}..."
            print(f"STATUS:{_pmsg}")
            sys.stdout.flush()
            log.info(_pmsg)
            fo.unmount(part)

        if image_option == 4:  # Ventoy
            from lufus.writing.install_ventoy import install_grub

            status_cb("Installing Ventoy bootloader...")
            progress_cb(10)
            success = install_grub(device_node)
            if success:
                progress_cb(100)
                status_cb("Ventoy installation complete")
            else:
                status_cb("Ventoy installation failed")
                log.error("Ventoy installation failed for device %s", device_node)
        else:  # Windows / Linux / Other / Format Only
            success = flash_usb(device_node, iso_path, progress_cb=progress_cb, status_cb=status_cb)

        log.info("flash_worker exiting, success=%s", success)
        sys.exit(0 if success else 1)
    finally:
        # Remove the PID file when done
        try:
            os.unlink(pid_file)
        except Exception:
            pass


if __name__ == "__main__":
    main()
