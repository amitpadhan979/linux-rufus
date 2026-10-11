"""
Interactive Terminal User Interface (TUI) for Linux Rufus.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

from linux_rufus.core.devices import DeviceManager, BlockDevice
from linux_rufus.core.iso import ISOInspector, ISOInfo
from linux_rufus.core.writers.base import WriteProgress
from linux_rufus.core.writers.raw_writer import RawWriter
from linux_rufus.core.writers.partition_writer import PartitionWriter
from linux_rufus.core.writers.windows_writer import WindowsWriter


def print_banner() -> None:
    """Print ASCII logo for Linux Rufus."""
    print("=" * 60)
    print("                LINUX RUFUS (v1.0.0)")
    print("     The Safety-First Bootable USB Creator for Linux")
    print("=" * 60)


def render_progress_bar(progress: WriteProgress) -> None:
    """Render a text progress bar in the terminal."""
    bar_width = 30
    filled = int(bar_width * (progress.percentage / 100.0))
    bar = "█" * filled + "░" * (bar_width - filled)
    sys.stdout.write(
        f"\r[{bar}] {progress.percentage:5.1f}% | {progress.speed_human} | ETA: {progress.eta_human} | {progress.status_text[:20]}"
    )
    sys.stdout.flush()


def run_interactive_tui() -> int:
    """Run interactive terminal menu workflow."""
    print_banner()

    # Step 1: Detect devices
    mgr = DeviceManager()
    devices = mgr.scan_devices()

    print("\n[1] Detecting Target USB Drives...")
    safe_devices = [d for d in devices if d.is_safe_target]

    if not safe_devices:
        print("  ✖ No safe removable USB drives detected.")
        print("  Please plug in a USB flash drive and re-run.")
        if any(not d.is_safe_target for d in devices):
            print("\n  Detected internal / system drives (LOCKED for safety):")
            for d in devices:
                print(f"    - {d.path} ({d.size_human}, Model: {d.model}, System: {d.is_system_disk})")
        return 1

    print("\n  Available Removable USB Drives:")
    for idx, dev in enumerate(safe_devices, 1):
        print(f"    {idx}. {dev.display_name}")

    selected_dev: Optional[BlockDevice] = None
    while not selected_dev:
        try:
            choice = input(f"\nSelect target device [1-{len(safe_devices)}] (or 'q' to quit): ").strip()
            if choice.lower() == "q":
                return 0
            dev_idx = int(choice) - 1
            if 0 <= dev_idx < len(safe_devices):
                selected_dev = safe_devices[dev_idx]
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a valid number.")

    # Step 2: Select ISO
    print("\n[2] Select Boot Image...")
    iso_path = ""
    while not iso_path:
        path_input = input("Enter path to ISO / IMG file: ").strip()
        clean_path = os.path.expanduser(path_input)
        if os.path.isfile(clean_path):
            iso_path = clean_path
        else:
            print(f"File not found: '{clean_path}'. Please try again.")

    inspector = ISOInspector(iso_path)
    info = inspector.inspect()

    print("\n  Image Analysis:")
    print(f"    - File: {os.path.basename(iso_path)} ({info.file_size_human})")
    print(f"    - Volume Label: {info.volume_id}")
    print(f"    - Type: {'Windows Installer' if info.is_windows else 'Linux Hybrid ISO' if info.is_hybrid else 'Standard ISO/IMG'}")
    print(f"    - Boot Support: UEFI={'Yes' if info.has_uefi else 'No'}, BIOS={'Yes' if info.has_bios else 'No'}")
    print(f"    - Recommended Mode: {info.recommended_mode.upper()}")

    # Step 3: Choose mode
    mode = info.recommended_mode
    print(f"\n[3] Burning Mode (Default: {mode.upper()}):")
    print("    1. DD / Raw Image Mode (Recommended for Linux Hybrid ISOs)")
    print("    2. Partition & Extract Mode (Recommended for Windows / UEFI FAT32)")
    mode_choice = input("Select mode [1/2, default matches image]: ").strip()
    if mode_choice == "1":
        mode = "raw"
    elif mode_choice == "2":
        mode = "partition"

    # Step 4: Final Confirmation Warning
    print("\n" + "!" * 60)
    print("WARNING: ALL DATA ON THE TARGET DRIVE WILL BE PERMANENTLY ERASED!")
    print(f"  Target:  {selected_dev.display_name}")
    print(f"  Image:   {iso_path}")
    print(f"  Mode:    {mode.upper()}")
    print("!" * 60)

    confirm = input("\nType 'YES' to proceed with wiping and burning: ").strip()
    if confirm != "YES":
        print("Operation aborted by user.")
        return 0

    print("\nUnmounting partitions and preparing drive...")
    DeviceManager.unmount_device(selected_dev.path)

    # Step 5: Execute Write
    print("\nStarting write operation...\n")
    start_time = time.time()

    try:
        if mode == "raw":
            writer = RawWriter(source_path=iso_path, target_device=selected_dev.path)
        elif info.is_windows:
            writer = WindowsWriter(source_path=iso_path, target_device=selected_dev.path)
        else:
            writer = PartitionWriter(
                source_path=iso_path,
                target_device=selected_dev.path,
                partition_scheme=info.recommended_partition_scheme,
                file_system="fat32",
                volume_label=info.volume_id,
            )

        success = writer.write(progress_callback=render_progress_bar)
        print("\n")
        if success:
            elapsed = time.time() - start_time
            print(f"✔ Completed successfully in {elapsed:.1f} seconds!")
            print("You can now safely eject your USB drive.")
            return 0
        else:
            print("✖ Write operation was cancelled or incomplete.")
            return 1
    except PermissionError:
        print("\n✖ Permission denied. Writing directly to block devices requires root/sudo privileges.")
        print(f"Try running: sudo linux-rufus burn --iso '{iso_path}' --target '{selected_dev.path}'")
        return 1
    except Exception as e:
        print(f"\n✖ Error during write operation: {e}")
        return 1
