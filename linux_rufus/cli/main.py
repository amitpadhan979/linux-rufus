"""
Command-line interface entry point for Linux Rufus.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from linux_rufus import __version__
from linux_rufus.core.devices import DeviceManager, SafetyViolationError
from linux_rufus.core.iso import ISOInspector
from linux_rufus.core.privilege import is_root
from linux_rufus.core.writers.base import WriteProgress
from linux_rufus.core.writers.raw_writer import RawWriter
from linux_rufus.core.writers.partition_writer import PartitionWriter
from linux_rufus.core.writers.windows_writer import WindowsWriter
from linux_rufus.cli.tui import render_progress_bar, run_interactive_tui


def command_list(args: argparse.Namespace) -> int:
    """List detected block devices with safety categorization."""
    mgr = DeviceManager(allow_non_removable=args.all)
    devices = mgr.scan_devices()

    dry_run_suffix = " [Dry-Run Mode]" if getattr(args, "dry_run", False) else ""
    print(f"\n--- Linux Rufus Block Device List ({len(devices)} detected){dry_run_suffix} ---")
    if not devices:
        print("No block devices found.")
        return 0

    has_safe = False
    for dev in devices:
        status = "✔ SAFE TARGET (Removable)" if dev.is_safe_target else "✖ LOCKED (System/Internal)"
        print(f"\nDevice:      {dev.path}")
        print(f"  Model:     {dev.vendor} {dev.model}".strip())
        print(f"  Capacity:  {dev.size_human} ({dev.size} bytes)")
        print(f"  Removable: {dev.removable} (Transport: {dev.transport or 'internal'})")
        print(f"  System:    {'YES (Contains critical mounts)' if dev.is_system_disk else 'No'}")
        if dev.mountpoints:
            print(f"  Mounts:    {', '.join(dev.mountpoints)}")
        print(f"  Status:    {status}")
        if dev.is_safe_target:
            has_safe = True

    print("\n" + "-" * 50)
    if not has_safe:
        print("Tip: If your USB drive isn't appearing as safe, ensure it is plugged in and removable.")
    return 0


def command_info(args: argparse.Namespace) -> int:
    """Analyze and display ISO metadata."""
    if not os.path.exists(args.iso):
        print(f"Error: ISO file '{args.iso}' does not exist.", file=sys.stderr)
        return 1

    inspector = ISOInspector(args.iso)
    info = inspector.inspect()

    print(f"\n--- ISO Analysis: {os.path.basename(args.iso)} ---")
    print(f"File Path:              {info.file_path}")
    print(f"File Size:              {info.file_size_human} ({info.file_size} bytes)")
    print(f"Volume Label:           {info.volume_id}")
    print(f"ISO9660 Standard:       {'Yes' if info.is_iso else 'No'}")
    print(f"Hybrid Boot (DD ready): {'Yes' if info.is_hybrid else 'No'}")
    print(f"Windows Media:          {'Yes' if info.is_windows else 'No'}")
    print(f"UEFI Support:           {'Yes' if info.has_uefi else 'No'}")
    print(f"BIOS / Legacy Support:  {'Yes' if info.has_bios else 'No'}")
    print(f"Recommended Mode:       {info.recommended_mode.upper()}")
    print(f"Recommended Scheme:     {info.recommended_partition_scheme}")
    print(f"Recommended Target:     {info.recommended_target_system}")
    print("-" * 50)
    return 0


def command_burn(args: argparse.Namespace) -> int:
    """Burn ISO to target USB device."""
    if not os.path.exists(args.iso):
        print(f"Error: ISO file '{args.iso}' does not exist.", file=sys.stderr)
        return 1

    # Safety validation
    mgr = DeviceManager(allow_non_removable=args.allow_internal)
    try:
        target_dev = mgr.validate_target_safety(args.target)
    except SafetyViolationError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    inspector = ISOInspector(args.iso)
    info = inspector.inspect()

    mode = args.mode or info.recommended_mode

    print(f"\nReady to write:")
    print(f"  Source:  {args.iso} ({info.file_size_human})")
    print(f"  Target:  {target_dev.display_name}")
    print(f"  Mode:    {mode.upper()}")

    if getattr(args, "dry_run", False):
        print("\n✔ [Dry-Run] Target safety validated and write parameters verified without hardware modification.")
        return 0

    # Require root for writing directly to block devices
    if not is_root():
        print(
            f"Error: Writing directly to {args.target} requires root privileges.",
            file=sys.stderr,
        )
        print(f"Please run with sudo: sudo linux-rufus burn --iso '{args.iso}' --target '{args.target}'", file=sys.stderr)
        return 1

    if not args.yes:
        print("\nWARNING: ALL DATA ON THE TARGET DEVICE WILL BE PERMANENTLY DESTROYED!")
        resp = input(f"Type 'yes' to confirm writing to {target_dev.path}: ")
        if resp.lower() != "yes":
            print("Aborted.")
            return 0

    print(f"\nUnmounting existing partitions on {target_dev.path}...")
    DeviceManager.unmount_device(target_dev.path)

    print("Beginning write operation...\n")
    start = time.time()

    if mode == "raw":
        writer = RawWriter(source_path=args.iso, target_device=target_dev.path)
    elif info.is_windows:
        writer = WindowsWriter(
            source_path=args.iso,
            target_device=target_dev.path,
            bypass_tpm=getattr(args, "bypass_tpm", False),
            bypass_ram=getattr(args, "bypass_ram", False),
            bypass_secure_boot=getattr(args, "bypass_secure_boot", False),
        )
    else:
        writer = PartitionWriter(
            source_path=args.iso,
            target_device=target_dev.path,
            partition_scheme=args.scheme or info.recommended_partition_scheme,
            file_system=args.fs or "fat32",
            volume_label=args.label or info.volume_id,
        )

    success = writer.write(progress_callback=render_progress_bar)
    print("\n")
    if success:
        elapsed = time.time() - start
        print(f"✔ Successfully written in {elapsed:.1f}s.")
        return 0
    else:
        print("✖ Write operation failed or was cancelled.", file=sys.stderr)
        return 1


def command_gui(args: argparse.Namespace) -> int:
    """Launch the Rufus-styled graphical interface."""
    from linux_rufus.gui.app import launch_gui
    return launch_gui()


def main() -> int:
    """Main CLI parser."""
    parser = argparse.ArgumentParser(
        prog="linux-rufus",
        description="A reliable, safety-first Linux utility inspired by Rufus for creating bootable USB flash drives.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: list
    parser_list = subparsers.add_parser("list", help="List detected removable USB devices safely")
    parser_list.add_argument("--all", action="store_true", help="Include internal non-removable drives in list")
    parser_list.add_argument("--dry-run", action="store_true", help="Perform verification check without making modifications")

    # Command: info
    parser_info = subparsers.add_parser("info", help="Inspect and display ISO file boot properties")
    parser_info.add_argument("iso", help="Path to ISO or image file")

    # Command: burn
    parser_burn = subparsers.add_parser("burn", help="Burn image file to target USB drive")
    parser_burn.add_argument("--iso", required=True, help="Path to source ISO or IMG file")
    parser_burn.add_argument("--target", required=True, help="Target device path (e.g. /dev/sdb)")
    parser_burn.add_argument("--mode", choices=["raw", "partition"], help="Writing mode (raw / partition)")
    parser_burn.add_argument("--scheme", choices=["GPT", "MBR"], help="Partition scheme (GPT / MBR)")
    parser_burn.add_argument("--fs", choices=["fat32", "ntfs", "exfat", "ext4"], help="Filesystem format")
    parser_burn.add_argument("--label", help="Custom volume label")
    parser_burn.add_argument("--allow-internal", action="store_true", help="Allow targeting internal drives (CAUTION)")
    parser_burn.add_argument("--bypass-tpm", action="store_true", help="Bypass Windows 11 TPM 2.0 and CPU checks")
    parser_burn.add_argument("--bypass-secure-boot", action="store_true", help="Bypass Windows 11 Secure Boot requirement")
    parser_burn.add_argument("--bypass-ram", action="store_true", help="Bypass Windows 11 minimum RAM (4GB) requirement")
    parser_burn.add_argument("--dry-run", action="store_true", help="Simulate burn verification without writing to hardware")
    parser_burn.add_argument("-y", "--yes", action="store_true", help="Skip interactive confirmation")

    # Command: gui
    subparsers.add_parser("gui", help="Launch Rufus graphical user interface")

    # Command: tui
    subparsers.add_parser("tui", help="Launch interactive text menu (TUI)")

    args = parser.parse_args()

    if args.command == "list":
        return command_list(args)
    elif args.command == "info":
        return command_info(args)
    elif args.command == "burn":
        return command_burn(args)
    elif args.command == "gui":
        return command_gui(args)
    elif args.command == "tui":
        return run_interactive_tui()
    else:
        # Default behavior with no arguments: if terminal, launch TUI, or print help
        if sys.stdin.isatty():
            return run_interactive_tui()
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
