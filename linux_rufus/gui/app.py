"""
Classic Rufus Desktop Graphical User Interface (GUI) for Linux.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import List, Optional

from linux_rufus.core.devices import DeviceManager, BlockDevice
from linux_rufus.core.iso import ISOInspector, ISOInfo
from linux_rufus.core.writers.base import WriteProgress
from linux_rufus.core.writers.raw_writer import RawWriter
from linux_rufus.core.writers.partition_writer import PartitionWriter
from linux_rufus.core.writers.windows_writer import WindowsWriter


def launch_gui() -> int:
    """Entry point for the GUI application."""
    # Check if graphical display server is available
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print(
            "Error: No graphical display server detected (DISPLAY/WAYLAND_DISPLAY is not set).",
            file=sys.stderr,
        )
        print("To use Linux Rufus in terminal/headless environments, run: linux-rufus tui", file=sys.stderr)
        return 1

    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except ImportError:
        print("Note: tkinter is not installed. Attempting PyQt6 fallback...", file=sys.stderr)
        return _launch_pyqt()

    return _launch_tkinter(tk, ttk, filedialog, messagebox)


def _launch_pyqt() -> int:
    """Fallback GUI using PyQt6 / PySide6 if available."""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
        except ImportError:
            print(
                "Error: Neither 'tkinter' nor 'PyQt6'/'PySide6' is installed.\n"
                "Please install python3-tk (e.g. sudo apt install python3-tk) or PyQt6 (pip install PyQt6).\n"
                "Alternatively, you can run the full interactive TUI mode with: linux-rufus tui",
                file=sys.stderr,
            )
            return 1
    return 0


def _launch_tkinter(tk, ttk, filedialog, messagebox) -> int:
    """Classic Rufus GUI implemented with Tkinter."""
    root = tk.Tk()
    root.title("Rufus 1.0.0 (Linux)")
    root.geometry("440x620")
    root.resizable(False, False)

    # Style configuration to mimic Rufus classic theme
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    mgr = DeviceManager()
    selected_device_var = tk.StringVar()
    boot_selection_var = tk.StringVar(value="Disk or ISO image (Please select)")
    partition_scheme_var = tk.StringVar(value="GPT")
    target_system_var = tk.StringVar(value="UEFI (non CSM)")
    volume_label_var = tk.StringVar(value="RUFUS_DRIVE")
    file_system_var = tk.StringVar(value="FAT32 (Default)")
    cluster_size_var = tk.StringVar(value="4096 bytes (Default)")
    status_label_var = tk.StringVar(value="READY")
    iso_path_var = tk.StringVar(value="")

    current_devices: List[BlockDevice] = []

    def refresh_devices():
        nonlocal current_devices
        current_devices = [d for d in mgr.scan_devices() if d.is_safe_target]
        dev_names = [d.display_name for d in current_devices]
        device_combo["values"] = dev_names
        if dev_names:
            device_combo.current(0)
            selected_device_var.set(dev_names[0])
        else:
            selected_device_var.set("No removable drives detected")

    # --- Frame: Drive Properties ---
    drive_frame = ttk.LabelFrame(root, text="Drive Properties", padding=(10, 8))
    drive_frame.pack(fill="x", padx=12, pady=6)

    ttk.Label(drive_frame, text="Device:").pack(anchor="w")
    dev_box = ttk.Frame(drive_frame)
    dev_box.pack(fill="x", pady=(2, 6))
    device_combo = ttk.Combobox(dev_box, textvariable=selected_device_var, state="readonly")
    device_combo.pack(side="left", fill="x", expand=True)
    refresh_btn = ttk.Button(dev_box, text="🔄", width=3, command=refresh_devices)
    refresh_btn.pack(side="right", padx=(4, 0))

    ttk.Label(drive_frame, text="Boot selection:").pack(anchor="w")
    boot_box = ttk.Frame(drive_frame)
    boot_box.pack(fill="x", pady=(2, 6))
    boot_entry = ttk.Entry(boot_box, textvariable=boot_selection_var, state="readonly")
    boot_entry.pack(side="left", fill="x", expand=True)

    def select_iso_file():
        path = filedialog.askopenfilename(
            title="Select ISO or Disk Image",
            filetypes=[
                ("Disk Images", "*.iso *.img *.raw"),
                ("All files", "*.*"),
            ],
        )
        if path:
            iso_path_var.set(path)
            boot_selection_var.set(os.path.basename(path))
            try:
                inspector = ISOInspector(path)
                info = inspector.inspect()
                volume_label_var.set(info.volume_id)
                partition_scheme_var.set(info.recommended_partition_scheme)
                target_system_var.set(info.recommended_target_system)
                status_label_var.set(f"Loaded {os.path.basename(path)} ({info.file_size_human})")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to analyze image: {e}")

    select_btn = ttk.Button(boot_box, text="SELECT", command=select_iso_file)
    select_btn.pack(side="right", padx=(4, 0))

    ttk.Label(drive_frame, text="Partition scheme:").pack(anchor="w")
    scheme_combo = ttk.Combobox(
        drive_frame,
        textvariable=partition_scheme_var,
        values=["GPT", "MBR"],
        state="readonly",
    )
    scheme_combo.pack(fill="x", pady=(2, 6))

    ttk.Label(drive_frame, text="Target system:").pack(anchor="w")
    target_combo = ttk.Combobox(
        drive_frame,
        textvariable=target_system_var,
        values=["UEFI (non CSM)", "BIOS (or UEFI-CSM)"],
        state="readonly",
    )
    target_combo.pack(fill="x", pady=(2, 6))

    # --- Frame: Format Options ---
    format_frame = ttk.LabelFrame(root, text="Format Options", padding=(10, 8))
    format_frame.pack(fill="x", padx=12, pady=6)

    ttk.Label(format_frame, text="Volume label:").pack(anchor="w")
    label_entry = ttk.Entry(format_frame, textvariable=volume_label_var)
    label_entry.pack(fill="x", pady=(2, 6))

    ttk.Label(format_frame, text="File system:").pack(anchor="w")
    fs_combo = ttk.Combobox(
        format_frame,
        textvariable=file_system_var,
        values=["FAT32 (Default)", "NTFS", "exFAT", "ext4"],
        state="readonly",
    )
    fs_combo.pack(fill="x", pady=(2, 6))

    ttk.Label(format_frame, text="Cluster size:").pack(anchor="w")
    cluster_combo = ttk.Combobox(
        format_frame,
        textvariable=cluster_size_var,
        values=["4096 bytes (Default)", "8192 bytes", "16 kilobytes"],
        state="readonly",
    )
    cluster_combo.pack(fill="x", pady=(2, 6))

    # --- Frame: Status & Progress ---
    status_frame = ttk.LabelFrame(root, text="Status", padding=(10, 8))
    status_frame.pack(fill="x", padx=12, pady=6)

    progress_bar = ttk.Progressbar(status_frame, orient="horizontal", mode="determinate")
    progress_bar.pack(fill="x", pady=(2, 4))

    status_lbl = ttk.Label(status_frame, textvariable=status_label_var, anchor="center")
    status_lbl.pack(fill="x")

    # --- Action Buttons ---
    btn_frame = ttk.Frame(root, padding=(12, 10))
    btn_frame.pack(fill="x", side="bottom")

    active_writer = [None]

    def on_start():
        if not iso_path_var.get() or not os.path.exists(iso_path_var.get()):
            messagebox.showwarning("No Image", "Please select an ISO or disk image first.")
            return

        if not current_devices:
            messagebox.showwarning("No Target", "No removable target USB drives available.")
            return

        selected_idx = device_combo.current()
        if selected_idx < 0 or selected_idx >= len(current_devices):
            messagebox.showwarning("Invalid Target", "Please select a valid USB target drive.")
            return

        target_dev = current_devices[selected_idx]

        # Confirmation dialog
        confirm = messagebox.askyesno(
            "WARNING: DATA DESTRUCTION",
            f"WARNING: ALL DATA ON DEVICE '{target_dev.display_name}' WILL BE DESTROYED.\n\n"
            "To continue with this operation, click YES. To quit click NO.",
            icon="warning",
        )
        if not confirm:
            return

        start_btn.config(state="disabled")
        refresh_btn.config(state="disabled")
        select_btn.config(state="disabled")

        def run_write():
            try:
                DeviceManager.unmount_device(target_dev.path)
                inspector = ISOInspector(iso_path_var.get())
                info = inspector.inspect()

                def update_cb(p: WriteProgress):
                    root.after(0, lambda: progress_bar.configure(value=p.percentage))
                    root.after(
                        0,
                        lambda: status_label_var.set(
                            f"{p.status_text} [{p.percentage:.1f}% - {p.speed_human}]"
                        ),
                    )

                if info.is_windows:
                    writer = WindowsWriter(source_path=iso_path_var.get(), target_device=target_dev.path)
                elif info.is_hybrid:
                    writer = RawWriter(source_path=iso_path_var.get(), target_device=target_dev.path)
                else:
                    writer = PartitionWriter(
                        source_path=iso_path_var.get(),
                        target_device=target_dev.path,
                        partition_scheme=partition_scheme_var.get(),
                        file_system="fat32",
                        volume_label=volume_label_var.get(),
                    )

                active_writer[0] = writer
                success = writer.write(progress_callback=update_cb)

                if success:
                    root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Rufus", "USB drive successfully created! You can now safely remove it."
                        ),
                    )
                    root.after(0, lambda: status_label_var.set("READY"))
                else:
                    root.after(0, lambda: status_label_var.set("CANCELLED"))

            except Exception as e:
                root.after(0, lambda: messagebox.showerror("Write Error", f"Error during write: {e}"))
                root.after(0, lambda: status_label_var.set("ERROR"))
            finally:
                root.after(0, lambda: start_btn.config(state="normal"))
                root.after(0, lambda: refresh_btn.config(state="normal"))
                root.after(0, lambda: select_btn.config(state="normal"))

        thread = threading.Thread(target=run_write, daemon=True)
        thread.start()

    start_btn = ttk.Button(btn_frame, text="START", command=on_start)
    start_btn.pack(side="right", padx=(6, 0))

    close_btn = ttk.Button(btn_frame, text="CLOSE", command=root.quit)
    close_btn.pack(side="right")

    refresh_devices()
    root.mainloop()
    return 0
