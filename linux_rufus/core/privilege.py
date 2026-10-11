"""
Privilege and authentication helpers for Linux Rufus.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def is_root() -> bool:
    """Return True if current process has root privileges (UID 0)."""
    return os.geteuid() == 0


def can_write_device(device_path: str) -> bool:
    """Check if current user has direct write access to the block device."""
    try:
        return os.access(device_path, os.W_OK)
    except Exception:
        return False


def elevate_command(cmd: list[str]) -> list[str]:
    """Prepend pkexec or sudo if running unprivileged."""
    if is_root():
        return cmd

    if shutil.which("pkexec") and os.environ.get("DISPLAY"):
        return ["pkexec"] + cmd
    if shutil.which("sudo"):
        return ["sudo"] + cmd

    return cmd


def ensure_elevated_or_relaunch() -> None:
    """Relaunches the current command with sudo/pkexec if not root."""
    if is_root():
        return

    launcher = None
    if shutil.which("pkexec") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        launcher = "pkexec"
    elif shutil.which("sudo"):
        launcher = "sudo"

    if launcher:
        args = [launcher, sys.executable] + sys.argv
        sys.exit(subprocess.call(args))
    else:
        sys.stderr.write("Error: Root privileges are required to write block devices.\n")
        sys.exit(1)
