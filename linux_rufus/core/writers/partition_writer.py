"""
Partition, format, and ISO extraction writer for Linux Rufus.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Callable, Optional

from linux_rufus.core.writers.base import BaseWriter, ProgressCallback, WriteProgress

logger = logging.getLogger(__name__)

PostExtractCallback = Callable[[str], None]


class PartitionWriter(BaseWriter):
    """
    Partition & Extract Writer (Rufus ISO mode).
    Creates MBR or GPT partition table, formats filesystem, extracts ISO files,
    and configures UEFI/BIOS boot structures.
    """

    def __init__(
        self,
        source_path: str,
        target_device: str,
        partition_scheme: str = "GPT",  # "GPT" or "MBR"
        file_system: str = "fat32",      # "fat32", "ntfs", "exfat", "ext4"
        volume_label: str = "RUFUS_USB",
        post_extract_callback: Optional[PostExtractCallback] = None,
        dry_run: bool = False,
        persistence_size_mb: int = 0,
    ) -> None:
        super().__init__(source_path, target_device)
        self.partition_scheme = partition_scheme.upper()
        self.file_system = file_system.lower()
        self.volume_label = volume_label[:11] if self.file_system == "fat32" else volume_label
        self.post_extract_callback = post_extract_callback
        self.dry_run = dry_run
        self.persistence_size_mb = persistence_size_mb

    def _get_partition_path(self, part_num: int = 1) -> str:
        """Derive partition device path (handles /dev/sdX1 vs /dev/nvme0n1p1)."""
        dev = self.target_device.rstrip("/")
        if dev[-1].isdigit():
            return f"{dev}p{part_num}"
        return f"{dev}{part_num}"

    def write(self, progress_callback: Optional[ProgressCallback] = None) -> bool:
        """Execute partitioning, formatting, and file extraction."""
        if not os.path.exists(self.source_path):
            raise FileNotFoundError(f"Source image '{self.source_path}' does not exist.")

        total_iso_size = os.path.getsize(self.source_path)

        def emit(pct: float, status: str) -> None:
            if progress_callback:
                progress_callback(
                    WriteProgress(
                        bytes_written=int((pct / 100.0) * total_iso_size),
                        total_bytes=total_iso_size,
                        percentage=pct,
                        speed_bytes_sec=0,
                        eta_seconds=0,
                        status_text=status,
                    )
                )

        if self.dry_run:
            emit(15.0, f"[Dry-Run] Simulating {self.partition_scheme} partition table creation...")
            emit(40.0, f"[Dry-Run] Simulating format to {self.file_system.upper()}...")
            emit(70.0, "[Dry-Run] Simulating ISO payload extraction...")
            if self.post_extract_callback:
                emit(85.0, "[Dry-Run] Simulating post-extraction hooks...")
            emit(100.0, "[Dry-Run] Simulated write completed successfully.")
            return True

        # Step 1: Wipe filesystem signatures
        emit(5.0, "Clearing existing disk signatures...")
        logger.info(f"Wiping signatures on {self.target_device}...")
        subprocess.run(["wipefs", "-a", self.target_device], capture_output=True)

        # Step 2: Create Partition Table
        emit(15.0, f"Creating {self.partition_scheme} partition table...")
        logger.info(f"Creating {self.partition_scheme} partition table on {self.target_device}...")

        # If persistence requested, calculate boundary
        if self.persistence_size_mb > 0:
            part1_end = f"-{self.persistence_size_mb}MiB"
        else:
            part1_end = "100%"

        if self.partition_scheme == "GPT":
            cmd = [
                "parted",
                "-s",
                self.target_device,
                "mklabel",
                "gpt",
                "mkpart",
                "primary",
                "fat32",
                "1MiB",
                part1_end,
                "set",
                "1",
                "esp",
                "on",
            ]
            if self.persistence_size_mb > 0:
                cmd.extend(["mkpart", "primary", "ext4", part1_end, "100%"])
            subprocess.run(cmd, check=True, capture_output=True)
        else:  # MBR / msdos
            cmd = [
                "parted",
                "-s",
                self.target_device,
                "mklabel",
                "msdos",
                "mkpart",
                "primary",
                "fat32",
                "1MiB",
                part1_end,
                "set",
                "1",
                "boot",
                "on",
            ]
            if self.persistence_size_mb > 0:
                cmd.extend(["mkpart", "primary", "ext4", part1_end, "100%"])
            subprocess.run(cmd, check=True, capture_output=True)

        # Allow kernel to register partitions
        subprocess.run(["partprobe", self.target_device], capture_output=True)
        time.sleep(1)

        partition_path = self._get_partition_path(1)

        # Step 3: Format Filesystem
        emit(25.0, f"Formatting {partition_path} as {self.file_system.upper()}...")
        logger.info(f"Formatting {partition_path} as {self.file_system}...")

        if self.file_system == "fat32":
            subprocess.run(
                ["mkfs.vfat", "-F", "32", "-n", self.volume_label, partition_path],
                check=True,
                capture_output=True,
            )
        elif self.file_system == "ntfs":
            subprocess.run(
                ["mkfs.ntfs", "-f", "-L", self.volume_label, partition_path],
                check=True,
                capture_output=True,
            )
        elif self.file_system == "ext4":
            subprocess.run(
                ["mkfs.ext4", "-F", "-L", self.volume_label, partition_path],
                check=True,
                capture_output=True,
            )
        else:
            raise ValueError(f"Unsupported filesystem: {self.file_system}")

        # Format secondary persistence partition if present
        if self.persistence_size_mb > 0:
            pers_part = self._get_partition_path(2)
            emit(35.0, f"Formatting persistence partition {pers_part} as EXT4 (casper-rw)...")
            logger.info(f"Formatting persistence partition {pers_part} as ext4...")
            subprocess.run(
                ["mkfs.ext4", "-F", "-L", "casper-rw", pers_part],
                check=True,
                capture_output=True,
            )

        # Step 4: Extract ISO Contents
        emit(40.0, "Mounting target filesystem...")
        target_mount = tempfile.mkdtemp(prefix="rufus_target_")
        iso_mount = tempfile.mkdtemp(prefix="rufus_iso_")

        try:
            # Mount target partition
            subprocess.run(["mount", partition_path, target_mount], check=True, capture_output=True)

            # Check if 7z is installed for direct extraction
            if shutil.which("7z"):
                emit(50.0, "Extracting ISO files with 7z...")
                subprocess.run(
                    ["7z", "x", f"-o{target_mount}", self.source_path, "-y"],
                    check=True,
                    capture_output=True,
                )
            else:
                # Mount ISO via loopback and copy
                emit(50.0, "Mounting ISO and copying files...")
                subprocess.run(
                    ["mount", "-o", "loop,ro", self.source_path, iso_mount],
                    check=True,
                    capture_output=True,
                )

                # Copy files recursively
                for root, dirs, files in os.walk(iso_mount):
                    rel_dir = os.path.relpath(root, iso_mount)
                    dest_dir = os.path.join(target_mount, rel_dir)
                    os.makedirs(dest_dir, exist_ok=True)
                    for file_name in files:
                        src_file = os.path.join(root, file_name)
                        dest_file = os.path.join(dest_dir, file_name)
                        shutil.copy2(src_file, dest_file)

            if self.post_extract_callback:
                emit(85.0, "Applying post-extraction configurations...")
                try:
                    self.post_extract_callback(target_mount)
                except Exception as cb_err:
                    logger.error(f"Post-extraction callback error: {cb_err}")

            emit(90.0, "Syncing files to drive...")
            subprocess.run(["sync"], check=True)

        finally:
            emit(95.0, "Unmounting temporary targets...")
            subprocess.run(["umount", "-f", iso_mount], capture_output=True)
            subprocess.run(["umount", "-f", target_mount], capture_output=True)
            shutil.rmtree(iso_mount, ignore_errors=True)
            shutil.rmtree(target_mount, ignore_errors=True)

        emit(100.0, "Completed successfully.")
        return True
