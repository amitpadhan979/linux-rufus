"""
Device discovery and safety verification engine for Linux Rufus.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# Critical system mountpoints that must NEVER be written to or destroyed
CRITICAL_MOUNTS = {
    "/",
    "/boot",
    "/boot/efi",
    "/home",
    "/etc",
    "/usr",
    "/var",
    "/root",
}


class SafetyViolationError(Exception):
    """Raised when an operation attempts to target an unsafe or system disk."""
    pass


@dataclass
class PartitionInfo:
    """Represents a disk partition."""
    path: str
    name: str
    size: int
    fstype: Optional[str] = None
    label: Optional[str] = None
    mountpoint: Optional[str] = None


@dataclass
class BlockDevice:
    """Represents a physical block device (e.g. USB flash drive, SSD)."""
    path: str
    name: str
    size: int
    model: str = "Unknown"
    vendor: str = ""
    removable: bool = False
    transport: str = ""
    mountpoints: List[str] = field(default_factory=list)
    partitions: List[PartitionInfo] = field(default_factory=list)
    is_system_disk: bool = False
    is_safe_target: bool = False

    @property
    def size_human(self) -> str:
        """Format bytes to human-readable string (KB, MB, GB, TB)."""
        bytes_val = float(self.size)
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if bytes_val < 1024.0 or unit == "PB":
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{self.size} B"

    @property
    def display_name(self) -> str:
        """User-friendly display label (e.g. '[16.0 GB] SanDisk Ultra (/dev/sdb)')."""
        name_part = f"{self.vendor} {self.model}".strip() or "Removable Drive"
        return f"[{self.size_human}] {name_part} ({self.path})"


class DeviceManager:
    """Manages discovery and safe selection of removable block devices."""

    def __init__(self, allow_non_removable: bool = False) -> None:
        self.allow_non_removable = allow_non_removable

    @staticmethod
    def get_system_mountpoints() -> set[str]:
        """Parse /proc/mounts and /proc/swaps to identify all active mount points."""
        mounts: set[str] = set()

        # Check /proc/mounts
        if os.path.exists("/proc/mounts"):
            try:
                with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            mounts.add(parts[1])
            except Exception as e:
                logger.debug(f"Could not read /proc/mounts: {e}")

        # Check /proc/swaps
        if os.path.exists("/proc/swaps"):
            try:
                with open("/proc/swaps", "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[1:]  # skip header
                    for line in lines:
                        parts = line.split()
                        if parts:
                            mounts.add(parts[0])
            except Exception as e:
                logger.debug(f"Could not read /proc/swaps: {e}")

        return mounts

    def scan_devices(self) -> List[BlockDevice]:
        """Scan system block devices using lsblk and filter out unsafe targets."""
        raw_devices = []
        # Attempt modern lsblk first (with MOUNTPOINTS), then fallback to legacy (MOUNTPOINT)
        for cols in [
            "NAME,KNAME,PATH,SIZE,ROTA,RM,MODEL,VENDOR,TRAN,MOUNTPOINTS,TYPE,FSTYPE,LABEL",
            "NAME,KNAME,PATH,SIZE,ROTA,RM,MODEL,VENDOR,TRAN,MOUNTPOINT,TYPE,FSTYPE,LABEL",
        ]:
            try:
                cmd = ["lsblk", "-J", "-b", "-o", cols]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                data = json.loads(result.stdout)
                raw_devices = data.get("blockdevices", [])
                break
            except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
                continue

        if not raw_devices:
            logger.warning("lsblk JSON queries failed or unavailable, attempting fallback scan.")
            return self._fallback_scan()

        system_mounts = self.get_system_mountpoints()
        devices: List[BlockDevice] = []

        for item in raw_devices:
            dev_type = item.get("type", "").lower()
            # Only consider top-level disks, loop/rom devices are excluded
            if dev_type != "disk":
                continue

            path = item.get("path") or f"/dev/{item.get('name', '')}"
            name = item.get("name", "")
            size = int(item.get("size") or 0)
            model = (item.get("model") or "").strip() or "Generic Drive"
            vendor = (item.get("vendor") or "").strip()
            rm_val = item.get("rm")
            removable = bool(rm_val is True or rm_val == 1 or str(rm_val).lower() == "true")
            transport = (item.get("tran") or "").lower()

            if transport == "usb":
                removable = True

            # Extract partitions and mountpoints (handles both modern list 'mountpoints' and legacy string 'mountpoint')
            mountpoints: List[str] = []
            if item.get("mountpoints"):
                mountpoints.extend([m for m in item.get("mountpoints", []) if m])
            elif item.get("mountpoint"):
                mountpoints.append(item.get("mountpoint"))

            partitions: List[PartitionInfo] = []
            has_critical_mount = any(m in CRITICAL_MOUNTS for m in mountpoints)

            for child in item.get("children", []):
                child_path = child.get("path") or f"/dev/{child.get('name', '')}"
                child_name = child.get("name", "")
                child_size = int(child.get("size") or 0)
                child_fstype = child.get("fstype")
                child_label = child.get("label")

                child_mounts: List[str] = []
                if child.get("mountpoints"):
                    child_mounts.extend([m for m in child.get("mountpoints", []) if m])
                elif child.get("mountpoint"):
                    child_mounts.append(child.get("mountpoint"))

                mountpoints.extend(child_mounts)
                if any(m in CRITICAL_MOUNTS for m in child_mounts):
                    has_critical_mount = True

                part_mp = child_mounts[0] if child_mounts else None
                partitions.append(
                    PartitionInfo(
                        path=child_path,
                        name=child_name,
                        size=child_size,
                        fstype=child_fstype,
                        label=child_label,
                        mountpoint=part_mp,
                    )
                )

            # Determine safety status
            is_system = has_critical_mount or any(m in system_mounts and m in CRITICAL_MOUNTS for m in mountpoints)
            
            # Target is safe if:
            # 1. It is removable or USB (or allow_non_removable is explicitly True)
            # 2. It does NOT host critical system mount points
            # 3. Size is greater than 0
            is_safe = (removable or self.allow_non_removable) and not is_system and size > 0

            device = BlockDevice(
                path=path,
                name=name,
                size=size,
                model=model,
                vendor=vendor,
                removable=removable,
                transport=transport,
                mountpoints=mountpoints,
                partitions=partitions,
                is_system_disk=is_system,
                is_safe_target=is_safe,
            )
            devices.append(device)

        return devices

    def _fallback_scan(self) -> List[BlockDevice]:
        """Fallback device scanner if lsblk JSON is unavailable."""
        devices: List[BlockDevice] = []
        sys_block = "/sys/block"
        names: List[str] = []
        proc_sizes: Dict[str, int] = {}

        # 1. Try reading /sys/block
        if os.path.exists(sys_block):
            try:
                names = os.listdir(sys_block)
            except (PermissionError, OSError) as pe:
                logger.warning(f"Could not read {sys_block} ({pe}), falling back to /proc/partitions.")

        # 2. If /sys/block is unreadable or empty, try /proc/partitions
        if not names and os.path.exists("/proc/partitions"):
            try:
                with open("/proc/partitions", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f.readlines()[2:]:
                        parts = line.split()
                        if len(parts) >= 4:
                            dev_name = parts[3]
                            # Filter out partitions (e.g. sda1 vs sda, nvme0n1p1 vs nvme0n1)
                            if re.match(r"^(sd[a-z]|hd[a-z]|vd[a-z]|xvd[a-z]|nvme\d+n\d+|mmcblk\d+)$", dev_name):
                                names.append(dev_name)
                                try:
                                    proc_sizes[dev_name] = int(parts[2]) * 1024
                                except ValueError:
                                    pass
            except Exception as e:
                logger.warning(f"Could not read /proc/partitions ({e}).")

        system_mounts = self.get_system_mountpoints()

        for name in names:
            if name.startswith(("loop", "ram", "sr", "dm-")):
                continue
            path = f"/dev/{name}"
            size = 0
            size_file = os.path.join(sys_block, name, "size")
            if os.path.exists(size_file):
                try:
                    with open(size_file, "r") as f:
                        size = int(f.read().strip()) * 512
                except Exception:
                    size = 0

            if size == 0 and name in proc_sizes:
                size = proc_sizes[name]

            if size == 0:
                try:
                    out = subprocess.check_output(
                        ["blockdev", "--getsize64", path], text=True, stderr=subprocess.DEVNULL
                    )
                    size = int(out.strip())
                except Exception:
                    pass

            removable = False
            rm_file = os.path.join(sys_block, name, "removable")
            if os.path.exists(rm_file):
                try:
                    with open(rm_file, "r") as f:
                        removable = f.read().strip() == "1"
                except Exception:
                    pass

            if not removable:
                try:
                    out = subprocess.check_output(
                        ["udevadm", "info", "-q", "property", "-n", path],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    )
                    if "ID_BUS=usb" in out or "ID_DRIVE_FLASH" in out:
                        removable = True
                except Exception:
                    pass

            is_safe = (removable or self.allow_non_removable) and size > 0

            devices.append(
                BlockDevice(
                    path=path,
                    name=name,
                    size=size,
                    removable=removable,
                    is_safe_target=is_safe,
                )
            )
        return devices

    def validate_target_safety(self, device_path: str) -> BlockDevice:
        """
        Rigorous safety validation for a target block device.
        Throws SafetyViolationError if the device is a system disk or unsafe.
        """
        clean_path = os.path.realpath(device_path)
        devices = self.scan_devices()

        target_dev = None
        for dev in devices:
            if os.path.realpath(dev.path) == clean_path:
                target_dev = dev
                break

        if not target_dev:
            # Check if this might be a valid block device path not in current scan
            if not os.path.exists(clean_path):
                raise SafetyViolationError(f"Target device '{device_path}' does not exist.")
            raise SafetyViolationError(
                f"Device '{clean_path}' could not be safely verified. Refusing to write."
            )

        if target_dev.is_system_disk:
            raise SafetyViolationError(
                f"CRITICAL SAFETY LOCK: Device '{target_dev.path}' contains active root or system "
                f"mountpoints ({target_dev.mountpoints}). Writing is forbidden!"
            )

        if not target_dev.removable and not self.allow_non_removable:
            raise SafetyViolationError(
                f"SAFETY LOCK: Device '{target_dev.path}' is marked as non-removable/internal. "
                "Use --allow-internal if you are completely sure."
            )

        return target_dev

    @staticmethod
    def unmount_device(device_path: str) -> None:
        """Unmount all mounted partitions of the specified block device."""
        try:
            # First try udisksctl or umount on any child partitions
            result = subprocess.run(
                ["lsblk", "-n", "-r", "-o", "PATH,MOUNTPOINTS", device_path],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    part_path = parts[0]
                    logger.info(f"Unmounting partition {part_path}...")
                    subprocess.run(["umount", "-f", part_path], capture_output=True)
        except Exception as e:
            logger.warning(f"Error while unmounting partitions on {device_path}: {e}")
