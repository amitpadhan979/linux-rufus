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


if __name__ == "__main__":
    unittest.main()
