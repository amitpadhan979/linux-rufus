"""
Raw image / DD stream writer for Linux Rufus.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from linux_rufus.core.writers.base import BaseWriter, ProgressCallback, WriteProgress

logger = logging.getLogger(__name__)


class RawWriter(BaseWriter):
    """
    Direct block writer (equivalent to Rufus DD mode).
    Streams source image blocks directly into target block device.
    """

    DEFAULT_BLOCK_SIZE = 4 * 1024 * 1024  # 4 MB chunk size

    def __init__(
        self,
        source_path: str,
        target_device: str,
        block_size: int = DEFAULT_BLOCK_SIZE,
        verify: bool = False,
    ) -> None:
        super().__init__(source_path, target_device)
        self.block_size = block_size
        self.verify = verify

    def write(self, progress_callback: Optional[ProgressCallback] = None) -> bool:
        """Stream source image directly to target device."""
        if not os.path.exists(self.source_path):
            raise FileNotFoundError(f"Source file '{self.source_path}' does not exist.")

        total_bytes = os.path.getsize(self.source_path)
        bytes_written = 0
        start_time = time.time()
        last_update_time = start_time

        logger.info(f"Starting raw write from {self.source_path} to {self.target_device}...")

        # Open source file for reading
        with open(self.source_path, "rb") as src:
            # Open target device with direct / raw flags where possible
            with open(self.target_device, "wb") as dst:
                while bytes_written < total_bytes:
                    if self.is_cancelled:
                        logger.warning("Write operation cancelled by user.")
                        return False

                    chunk = src.read(self.block_size)
                    if not chunk:
                        break

                    dst.write(chunk)
                    bytes_written += len(chunk)

                    now = time.time()
                    # Throttle progress callbacks to ~10 times per second
                    if progress_callback and (now - last_update_time >= 0.1 or bytes_written == total_bytes):
                        elapsed = now - start_time
                        speed = bytes_written / elapsed if elapsed > 0 else 0
                        remaining_bytes = total_bytes - bytes_written
                        eta = remaining_bytes / speed if speed > 0 else 0
                        pct = (bytes_written / total_bytes) * 100.0

                        progress = WriteProgress(
                            bytes_written=bytes_written,
                            total_bytes=total_bytes,
                            percentage=pct,
                            speed_bytes_sec=speed,
                            eta_seconds=eta,
                            status_text=f"Writing image ({pct:.1f}%)...",
                        )
                        progress_callback(progress)
                        last_update_time = now

                # Sync buffers to ensure all blocks are safely written to physical flash
                if progress_callback:
                    progress_callback(
                        WriteProgress(
                            bytes_written=bytes_written,
                            total_bytes=total_bytes,
                            percentage=100.0,
                            speed_bytes_sec=0,
                            eta_seconds=0,
                            status_text="Flushing kernel disk buffers (sync)...",
                        )
                    )

                dst.flush()
                try:
                    os.fdatasync(dst.fileno())
                except OSError:
                    os.sync()

        # Step 2: Post-write verification if requested
        if self.verify:
            logger.info(f"Verifying written data on {self.target_device} against {self.source_path}...")
            if progress_callback:
                progress_callback(
                    WriteProgress(
                        bytes_written=0,
                        total_bytes=total_bytes,
                        percentage=0.0,
                        speed_bytes_sec=0,
                        eta_seconds=0,
                        status_text="Verifying written image...",
                    )
                )

            verified_bytes = 0
            v_start = time.time()
            v_last_update = v_start

            with open(self.source_path, "rb") as src, open(self.target_device, "rb") as dst:
                while verified_bytes < total_bytes:
                    if self.is_cancelled:
                        logger.warning("Verification cancelled by user.")
                        return False

                    src_chunk = src.read(self.block_size)
                    dst_chunk = dst.read(len(src_chunk))

                    if src_chunk != dst_chunk:
                        logger.error(
                            f"Verification mismatch at offset {verified_bytes} bytes! Written data is corrupted."
                        )
                        return False

                    verified_bytes += len(src_chunk)
                    now = time.time()
                    if progress_callback and (now - v_last_update >= 0.1 or verified_bytes == total_bytes):
                        elapsed = now - v_start
                        speed = verified_bytes / elapsed if elapsed > 0 else 0
                        remaining = total_bytes - verified_bytes
                        eta = remaining / speed if speed > 0 else 0
                        pct = (verified_bytes / total_bytes) * 100.0

                        progress_callback(
                            WriteProgress(
                                bytes_written=verified_bytes,
                                total_bytes=total_bytes,
                                percentage=pct,
                                speed_bytes_sec=speed,
                                eta_seconds=eta,
                                status_text=f"Verifying ({pct:.1f}%)...",
                            )
                        )
                        v_last_update = now

            logger.info("Verification passed: written data matches source image perfectly.")

        logger.info(f"Successfully wrote {bytes_written} bytes to {self.target_device}")
        return True
