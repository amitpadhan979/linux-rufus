"""
ISO Inspection and Boot Media Classifier for Linux Rufus.
"""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass
from typing import Optional


@dataclass
class ISOInfo:
    """Detailed metadata and boot capabilities for an image file."""
    file_path: str
    file_size: int
    volume_id: str = "BOOT_MEDIA"
    is_iso: bool = False
    is_hybrid: bool = False
    is_windows: bool = False
    has_uefi: bool = False
    has_bios: bool = False
    recommended_mode: str = "raw"  # "raw" (DD) or "partition" (Extract)
    recommended_partition_scheme: str = "GPT"  # "GPT" or "MBR"
    recommended_target_system: str = "UEFI (non CSM)"  # "UEFI" or "BIOS"
    sha256: Optional[str] = None
    md5: Optional[str] = None

    @property
    def file_size_human(self) -> str:
        """Human-readable size format."""
        bytes_val = float(self.file_size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_val < 1024.0 or unit == "TB":
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{self.file_size} B"


class ISOInspector:
    """Analyzes ISO/IMG files to identify boot structures, hybrid signatures, and OS type."""

    ISO_SECTOR_SIZE = 2048
    PVD_OFFSET = 16 * ISO_SECTOR_SIZE  # 32768 (Sector 16)

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def compute_hashes(self, block_size: int = 1024 * 1024) -> tuple[str, str]:
        """Compute (sha256, md5) checksums of the image file."""
        sha256_hash = hashlib.sha256()
        md5_hash = hashlib.md5()
        with open(self.file_path, "rb") as f:
            while chunk := f.read(block_size):
                sha256_hash.update(chunk)
                md5_hash.update(chunk)
        return sha256_hash.hexdigest(), md5_hash.hexdigest()

    def inspect(self, compute_hash: bool = False) -> ISOInfo:
        """Analyze the image file and return ISOInfo."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Image file not found: {self.file_path}")

        file_size = os.path.getsize(self.file_path)
        sha256_val, md5_val = None, None
        if compute_hash:
            sha256_val, md5_val = self.compute_hashes()

        info = ISOInfo(
            file_path=self.file_path,
            file_size=file_size,
            sha256=sha256_val,
            md5=md5_val,
        )

        if file_size < 32768:
            # File too small to be a standard ISO
            return info

        with open(self.file_path, "rb") as f:
            # 1. Check for MBR boot signature at offset 510 (0x55AA)
            mbr_header = f.read(512)
            has_mbr_sig = len(mbr_header) == 512 and mbr_header[510:512] == b"\x55\xaa"

            # Check for partition entries in MBR (offsets 0x1BE, 0x1CE, 0x1DE, 0x1EE)
            has_valid_partitions = False
            if has_mbr_sig:
                for offset in (0x1BE, 0x1CE, 0x1DE, 0x1EE):
                    part_type = mbr_header[offset + 4]
                    if part_type != 0x00:
                        has_valid_partitions = True
                        break

            # 2. Check ISO9660 Primary Volume Descriptor at sector 16 (offset 32768)
            f.seek(self.PVD_OFFSET)
            pvd_sector = f.read(self.ISO_SECTOR_SIZE)
            is_iso9660 = False
            volume_label = ""

            if len(pvd_sector) >= 6:
                # Type 1 = Primary Volume Descriptor, Identifier = 'CD001'
                if pvd_sector[0] == 1 and pvd_sector[1:6] == b"CD001":
                    is_iso9660 = True
                    # Volume identifier is 32 bytes at offset 40
                    raw_label = pvd_sector[40:72].decode("utf-8", errors="ignore").strip()
                    if raw_label:
                        volume_label = raw_label

            # 3. Scan El Torito and UDF / EFI markers
            f.seek(0)
            sample_header = f.read(min(file_size, 4 * 1024 * 1024))  # Read first 4MB

            has_efi_marker = (
                b"EFI" in sample_header
                or b"BOOTX64.EFI" in sample_header.upper()
                or b"EL TORITO SPECIFICATION" in sample_header
            )
            has_bios_marker = has_mbr_sig or is_iso9660

            # 4. Check for Windows signatures
            is_windows = (
                b"INSTALL.WIM" in sample_header.upper()
                or b"INSTALL.ESD" in sample_header.upper()
                or b"SOURCES\\BOOT.WIM" in sample_header.upper()
                or b"MICROSOFT WINDOWS" in sample_header.upper()
                or "WIN" in volume_label.upper()
                and ("10" in volume_label or "11" in volume_label or "SERVER" in volume_label)
            )

            # 5. Hybrid ISO detection (MBR partition table + ISO9660)
            is_hybrid = is_iso9660 and has_valid_partitions

            info.is_iso = is_iso9660
            info.volume_id = volume_label or os.path.splitext(os.path.basename(self.file_path))[0]
            info.is_hybrid = is_hybrid
            info.is_windows = is_windows
            info.has_uefi = has_efi_marker or is_windows
            info.has_bios = has_bios_marker

            # Formulate recommendations
            if is_windows:
                info.recommended_mode = "partition"
                info.recommended_partition_scheme = "GPT"
                info.recommended_target_system = "UEFI (non CSM)"
            elif is_hybrid:
                info.recommended_mode = "raw"
                info.recommended_partition_scheme = "MBR"
                info.recommended_target_system = "BIOS or UEFI"
            else:
                info.recommended_mode = "raw"
                info.recommended_partition_scheme = "MBR"
                info.recommended_target_system = "BIOS"

        return info
