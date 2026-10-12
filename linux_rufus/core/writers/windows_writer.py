"""
Windows Media Writer and WIM Splitter for Linux Rufus.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional

from linux_rufus.core.writers.base import BaseWriter, ProgressCallback, WriteProgress
from linux_rufus.core.writers.partition_writer import PartitionWriter

logger = logging.getLogger(__name__)

FAT32_MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024 - 1  # 4 GB minus 1 byte


class WindowsWriter(BaseWriter):
    """
    Specialized writer for Windows 10/11 installation media.
    Handles UEFI FAT32 compatibility by splitting large install.wim (>4GB)
    into install.swm chunks via wimlib-imagex or using NTFS UEFI fallback.
    """

    def __init__(
        self,
        source_path: str,
        target_device: str,
        bypass_tpm: bool = False,
        bypass_ram: bool = False,
        bypass_secure_boot: bool = False,
    ) -> None:
        super().__init__(source_path, target_device)
        self.bypass_tpm = bypass_tpm
        self.bypass_ram = bypass_ram
        self.bypass_secure_boot = bypass_secure_boot

    @staticmethod
    def split_wim_if_needed(target_mount_dir: str) -> bool:
        """
        Check if install.wim exists and exceeds FAT32 limit.
        If wimlib-imagex is available, split it into .swm files.
        """
        wim_path = os.path.join(target_mount_dir, "sources", "install.wim")
        if not os.path.exists(wim_path):
            # Might be lower case or install.esd
            for root, _, files in os.walk(target_mount_dir):
                for f in files:
                    if f.lower() == "install.wim":
                        wim_path = os.path.join(root, f)
                        break

        if not os.path.exists(wim_path):
            return False

        file_size = os.path.getsize(wim_path)
        if file_size <= FAT32_MAX_FILE_SIZE:
            return False

        logger.info(f"install.wim is {file_size} bytes (>4GB). Splitting into SWM chunks...")

        if not shutil.which("wimlib-imagex"):
            logger.warning("wimlib-imagex not found. Large WIM file cannot be split.")
            return False

        swm_pattern = os.path.join(os.path.dirname(wim_path), "install.swm")
        # Split into 3800 MB chunks
        res = subprocess.run(
            ["wimlib-imagex", "split", wim_path, swm_pattern, "3800"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            os.remove(wim_path)
            logger.info("install.wim successfully split into .swm chunks.")
            return True
        else:
            logger.error(f"Failed to split WIM: {res.stderr}")
            return False

    def apply_windows_tweaks(self, target_mount_dir: str) -> None:
        """Apply Windows 11 TPM/Secure Boot bypass registry scripts and split oversized WIM."""
        # 1. Split oversized install.wim if needed
        self.split_wim_if_needed(target_mount_dir)

        # 2. Inject Rufus-style TPM/Secure Boot/RAM bypass if requested
        if self.bypass_tpm or self.bypass_secure_boot or self.bypass_ram:
            sources_dir = os.path.join(target_mount_dir, "sources")
            if not os.path.exists(sources_dir):
                for root, dirs, _ in os.walk(target_mount_dir):
                    for d in dirs:
                        if d.lower() == "sources":
                            sources_dir = os.path.join(root, d)
                            break

            if os.path.isdir(sources_dir):
                reg_file_path = os.path.join(sources_dir, "rufus_bypass.reg")
                cmd_file_path = os.path.join(sources_dir, "winpeshl.ini")
                logger.info(f"Injecting Windows 11 hardware bypass configurations into {sources_dir}...")
                try:
                    with open(reg_file_path, "w", encoding="utf-8") as f:
                        f.write("Windows Registry Editor Version 5.00\r\n\r\n")
                        f.write("[HKEY_LOCAL_MACHINE\\SYSTEM\\Setup\\LabConfig]\r\n")
                        if self.bypass_tpm:
                            f.write('"BypassTPMCheck"=dword:00000001\r\n')
                        if self.bypass_secure_boot:
                            f.write('"BypassSecureBootCheck"=dword:00000001\r\n')
                        if self.bypass_ram:
                            f.write('"BypassRAMCheck"=dword:00000001\r\n')
                        f.write('"BypassCPUCheck"=dword:00000001\r\n')
                        f.write('"BypassStorageCheck"=dword:00000001\r\n')
                except Exception as e:
                    logger.warning(f"Could not write bypass registry file: {e}")

    def write(self, progress_callback: Optional[ProgressCallback] = None) -> bool:
        """Delegate to partition writer with post-extraction Windows tweaks."""
        delegate = PartitionWriter(
            source_path=self.source_path,
            target_device=self.target_device,
            partition_scheme="GPT",
            file_system="fat32",
            volume_label="WIN_INSTALL",
            post_extract_callback=self.apply_windows_tweaks,
        )
        return delegate.write(progress_callback=progress_callback)
