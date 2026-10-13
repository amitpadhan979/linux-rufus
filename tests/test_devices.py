"""
Unit tests for DeviceManager and safety validations.
"""

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from linux_rufus.core.devices import (
    BlockDevice,
    DeviceManager,
    PartitionInfo,
    SafetyViolationError,
)


class TestDevices(unittest.TestCase):
    def test_block_device_size_human(self):
        dev = BlockDevice(path="/dev/sdb", name="sdb", size=16 * 1024 * 1024 * 1024)
        self.assertEqual(dev.size_human, "16.0 GB")

        dev_small = BlockDevice(path="/dev/sdc", name="sdc", size=512)
        self.assertEqual(dev_small.size_human, "512.0 B")

    def test_block_device_safety_flags(self):
        # A removable USB disk without system mount points is safe
        safe_dev = BlockDevice(
            path="/dev/sdb",
            name="sdb",
            size=8 * 1024 * 1024 * 1024,
            removable=True,
            transport="usb",
            is_system_disk=False,
            is_safe_target=True,
        )
        self.assertTrue(safe_dev.is_safe_target)
        self.assertFalse(safe_dev.is_system_disk)

        # An internal drive with / mounted is NOT safe
        unsafe_dev = BlockDevice(
            path="/dev/sda",
            name="sda",
            size=500 * 1024 * 1024 * 1024,
            removable=False,
            transport="sata",
            mountpoints=["/"],
            is_system_disk=True,
            is_safe_target=False,
        )
        self.assertFalse(unsafe_dev.is_safe_target)
        self.assertTrue(unsafe_dev.is_system_disk)

    @patch("subprocess.run")
    def test_device_manager_scan_filters(self, mock_run):
        # Mock lsblk JSON output
        mock_output = {
            "blockdevices": [
                {
                    "name": "sda",
                    "path": "/dev/sda",
                    "type": "disk",
                    "size": 512110190592,
                    "rm": False,
                    "tran": "sata",
                    "model": "Samsung SSD 970",
                    "vendor": "Samsung",
                    "mountpoints": [],
                    "children": [
                        {"name": "sda1", "path": "/dev/sda1", "size": 512110190592, "mountpoints": ["/"]}
                    ],
                },
                {
                    "name": "sdb",
                    "path": "/dev/sdb",
                    "type": "disk",
                    "size": 32000000000,
                    "rm": True,
                    "tran": "usb",
                    "model": "Ultra Fit",
                    "vendor": "SanDisk",
                    "mountpoints": [],
                    "children": [],
                },
            ]
        }
        mock_res = MagicMock()
        mock_res.stdout = __import__("json").dumps(mock_output)
        mock_run.return_value = mock_res

        mgr = DeviceManager()
        devices = mgr.scan_devices()

        self.assertEqual(len(devices), 2)

        sda = next(d for d in devices if d.name == "sda")
        self.assertTrue(sda.is_system_disk)
        self.assertFalse(sda.is_safe_target)

        sdb = next(d for d in devices if d.name == "sdb")
        self.assertFalse(sdb.is_system_disk)
        self.assertTrue(sdb.is_safe_target)

    @patch.object(DeviceManager, "scan_devices")
    def test_validate_target_safety_exception(self, mock_scan):
        system_dev = BlockDevice(
            path="/dev/sda",
            name="sda",
            size=1000000,
            mountpoints=["/"],
            is_system_disk=True,
            is_safe_target=False,
        )
        mock_scan.return_value = [system_dev]

        mgr = DeviceManager()
        with self.assertRaises(SafetyViolationError):
            mgr.validate_target_safety("/dev/sda")

    @patch("subprocess.run")
    @patch("os.listdir", side_effect=PermissionError("Permission denied: /sys/block"))
    @patch("os.path.exists", return_value=True)
    def test_scan_devices_fallback_permission_denied(self, mock_exists, mock_listdir, mock_run):
        # Simulate lsblk failing with exit code 1
        mock_run.side_effect = subprocess.CalledProcessError(1, ["lsblk"])
        mgr = DeviceManager()
        # Must not raise PermissionError or CalledProcessError
        devices = mgr.scan_devices()
        self.assertIsInstance(devices, list)

    @patch("subprocess.run")
    def test_lsblk_legacy_singular_mountpoint(self, mock_run):
        # Older lsblk output with singular 'mountpoint' instead of 'mountpoints'
        mock_output = {
            "blockdevices": [
                {
                    "name": "sdb",
                    "path": "/dev/sdb",
                    "size": 16000000000,
                    "rm": True,
                    "tran": "usb",
                    "type": "disk",
                    "mountpoint": None,
                    "children": [
                        {
                            "name": "sdb1",
                            "path": "/dev/sdb1",
                            "size": 16000000000,
                            "type": "part",
                            "mountpoint": "/media/usb",
                        }
                    ],
                }
            ]
        }
        mock_res = MagicMock()
        mock_res.stdout = __import__("json").dumps(mock_output)
        mock_run.return_value = mock_res

        mgr = DeviceManager()
        devices = mgr.scan_devices()
        self.assertEqual(len(devices), 1)
        self.assertIn("/media/usb", devices[0].mountpoints)
        self.assertTrue(devices[0].is_safe_target)


if __name__ == "__main__":
    unittest.main()
