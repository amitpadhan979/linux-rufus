"""
Base writer interface and progress data model for Linux Rufus.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class WriteProgress:
    """Snapshot of active write operation progress."""
    bytes_written: int
    total_bytes: int
    percentage: float
    speed_bytes_sec: float
    eta_seconds: float
    status_text: str = ""

    @property
    def speed_human(self) -> str:
        """Formatted transfer speed (e.g. 24.5 MB/s)."""
        speed = float(self.speed_bytes_sec)
        for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
            if speed < 1024.0 or unit == "GB/s":
                return f"{speed:.1f} {unit}"
            speed /= 1024.0
        return f"{self.speed_bytes_sec:.1f} B/s"

    @property
    def eta_human(self) -> str:
        """Formatted estimated time remaining."""
        if self.eta_seconds <= 0 or self.eta_seconds > 86400:
            return "--:--"
        mins, secs = divmod(int(self.eta_seconds), 60)
        hrs, mins = divmod(mins, 60)
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"


ProgressCallback = Callable[[WriteProgress], None]


class BaseWriter(ABC):
    """Abstract base class for disk writers."""

    def __init__(self, source_path: str, target_device: str) -> None:
        self.source_path = source_path
        self.target_device = target_device
        self._is_cancelled = False

    def cancel(self) -> None:
        """Signal cancellation of the current writing task."""
        self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._is_cancelled

    @abstractmethod
    def write(self, progress_callback: Optional[ProgressCallback] = None) -> bool:
        """Execute the write process to the target device."""
        pass
