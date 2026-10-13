"""
Unit tests for CLI interface and parsing.
"""

import sys
import unittest
from unittest.mock import patch

from linux_rufus.cli.main import main


class TestCLI(unittest.TestCase):
    def test_cli_help(self):
        with patch.object(sys, "argv", ["linux-rufus", "--help"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 0)

    def test_cli_version(self):
        with patch.object(sys, "argv", ["linux-rufus", "--version"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 0)

    @patch("linux_rufus.core.devices.DeviceManager.scan_devices")
    def test_cli_list(self, mock_scan):
        mock_scan.return_value = []
        with patch.object(sys, "argv", ["linux-rufus", "list"]):
            ret = main()
            self.assertEqual(ret, 0)

    @patch("linux_rufus.core.devices.DeviceManager.scan_devices")
    def test_cli_list_dry_run(self, mock_scan):
        mock_scan.return_value = []
        with patch.object(sys, "argv", ["linux-rufus", "list", "--dry-run"]):
            ret = main()
            self.assertEqual(ret, 0)

    @patch("os.path.exists", return_value=True)
    @patch("linux_rufus.core.devices.DeviceManager.validate_target_safety")
    @patch("linux_rufus.core.iso.ISOInspector.inspect")
    def test_cli_burn_dry_run(self, mock_inspect, mock_validate, mock_exists):
        from linux_rufus.core.devices import BlockDevice
        from linux_rufus.core.iso import ISOInfo

        mock_validate.return_value = BlockDevice(
            name="sdb",
            path="/dev/sdb",
            size=16000000000,
            removable=True,
            model="Flash Drive",
            vendor="SanDisk",
        )
        mock_inspect.return_value = ISOInfo(
            file_path="test.iso",
            file_size=1000000,
            volume_id="TEST_ISO",
            is_iso=True,
            is_hybrid=True,
            has_uefi=True,
            has_bios=True,
            is_windows=False,
            recommended_mode="raw",
            recommended_partition_scheme="GPT",
            recommended_target_system="UEFI",
        )

        with patch.object(sys, "argv", ["linux-rufus", "burn", "--iso", "test.iso", "--target", "/dev/sdb", "--dry-run"]):
            ret = main()
            self.assertEqual(ret, 0)

    @patch("os.path.exists", return_value=True)
    @patch("linux_rufus.core.devices.DeviceManager.validate_target_safety")
    @patch("linux_rufus.core.iso.ISOInspector.inspect")
    def test_cli_burn_windows_bypass(self, mock_inspect, mock_validate, mock_exists):
        from linux_rufus.core.devices import BlockDevice
        from linux_rufus.core.iso import ISOInfo

        mock_validate.return_value = BlockDevice(
            name="sdb",
            path="/dev/sdb",
            size=16000000000,
            removable=True,
            model="Flash Drive",
            vendor="SanDisk",
        )
        mock_inspect.return_value = ISOInfo(
            file_path="Win11.iso",
            file_size=5000000000,
            volume_id="WIN11_INSTALL",
            is_iso=True,
            is_hybrid=False,
            has_uefi=True,
            has_bios=False,
            is_windows=True,
            recommended_mode="partition",
            recommended_partition_scheme="GPT",
            recommended_target_system="UEFI (non CSM)",
        )

        with patch.object(
            sys,
            "argv",
            [
                "linux-rufus",
                "burn",
                "--iso",
                "Win11.iso",
                "--target",
                "/dev/sdb",
                "--bypass-tpm",
                "--bypass-secure-boot",
                "--dry-run",
            ],
        ):
            ret = main()
            self.assertEqual(ret, 0)

    @patch("os.path.exists", return_value=True)
    @patch("linux_rufus.core.iso.ISOInspector.inspect")
    def test_cli_info_hash(self, mock_inspect, mock_exists):
        from linux_rufus.core.iso import ISOInfo
        mock_inspect.return_value = ISOInfo(
            file_path="ubuntu.iso",
            file_size=2000000000,
            volume_id="UBUNTU_2404",
            sha256="abcdef1234567890",
            md5="1234567890abcdef",
        )
        with patch.object(sys, "argv", ["linux-rufus", "info", "ubuntu.iso", "--hash"]):
            ret = main()
            self.assertEqual(ret, 0)

    @patch("os.path.exists", return_value=True)
    @patch("linux_rufus.core.devices.DeviceManager.validate_target_safety")
    @patch("linux_rufus.core.iso.ISOInspector.inspect")
    def test_cli_burn_verify_and_persistence(self, mock_inspect, mock_validate, mock_exists):
        from linux_rufus.core.devices import BlockDevice
        from linux_rufus.core.iso import ISOInfo

        mock_validate.return_value = BlockDevice(
            name="sdb",
            path="/dev/sdb",
            size=16000000000,
            removable=True,
            model="Flash Drive",
            vendor="SanDisk",
        )
        mock_inspect.return_value = ISOInfo(
            file_path="ubuntu.iso",
            file_size=2000000000,
            volume_id="UBUNTU",
            is_iso=True,
            is_hybrid=True,
            has_uefi=True,
            has_bios=True,
            is_windows=False,
            recommended_mode="raw",
            recommended_partition_scheme="MBR",
            recommended_target_system="BIOS or UEFI",
        )

        with patch.object(
            sys,
            "argv",
            [
                "linux-rufus",
                "burn",
                "--iso",
                "ubuntu.iso",
                "--target",
                "/dev/sdb",
                "--verify",
                "--persistence-size",
                "2G",
                "--dry-run",
            ],
        ):
            ret = main()
            self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
