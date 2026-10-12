"""
Unit tests for writers and progress reporting.
"""

import os
import tempfile
import unittest

from linux_rufus.core.writers.base import WriteProgress
from linux_rufus.core.writers.raw_writer import RawWriter


class TestWriters(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.temp_dir):
            try:
                os.remove(os.path.join(self.temp_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_write_progress_human_formats(self):
        prog = WriteProgress(
            bytes_written=500 * 1024 * 1024,
            total_bytes=1000 * 1024 * 1024,
            percentage=50.0,
            speed_bytes_sec=25 * 1024 * 1024,  # 25 MB/s
            eta_seconds=20,
            status_text="Writing...",
        )
        self.assertEqual(prog.speed_human, "25.0 MB/s")
        self.assertEqual(prog.eta_human, "00:20")

    def test_raw_writer_streaming(self):
        src_path = os.path.join(self.temp_dir, "test_source.bin")
        dst_path = os.path.join(self.temp_dir, "test_target.bin")

        payload = b"A" * (1024 * 1024)  # 1MB
        with open(src_path, "wb") as f:
            f.write(payload)

        progress_events = []

        def on_progress(p: WriteProgress):
            progress_events.append(p)

        writer = RawWriter(
            source_path=src_path,
            target_device=dst_path,
            block_size=128 * 1024,
        )
        success = writer.write(progress_callback=on_progress)

        self.assertTrue(success)
        self.assertTrue(os.path.exists(dst_path))
        self.assertEqual(os.path.getsize(dst_path), len(payload))

        with open(dst_path, "rb") as f:
            self.assertEqual(f.read(), payload)

        self.assertTrue(len(progress_events) > 0)
        self.assertEqual(progress_events[-1].percentage, 100.0)

    def test_raw_writer_cancel(self):
        src_path = os.path.join(self.temp_dir, "cancel_source.bin")
        dst_path = os.path.join(self.temp_dir, "cancel_target.bin")

        with open(src_path, "wb") as f:
            f.write(b"B" * (2 * 1024 * 1024))

        writer = RawWriter(source_path=src_path, target_device=dst_path)
        writer.cancel()
        success = writer.write()
        self.assertFalse(success)

    def test_partition_writer_dry_run(self):
        from linux_rufus.core.writers.partition_writer import PartitionWriter

        src_path = os.path.join(self.temp_dir, "fake_iso.iso")
        with open(src_path, "wb") as f:
            f.write(b"ISO PAYLOAD")

        events = []
        writer = PartitionWriter(
            source_path=src_path,
            target_device="/dev/null",
            dry_run=True,
            post_extract_callback=lambda p: None,
        )
        success = writer.write(progress_callback=lambda p: events.append(p))
        self.assertTrue(success)
        self.assertTrue(any("Dry-Run" in e.status_text for e in events))
        self.assertEqual(events[-1].percentage, 100.0)

    def test_windows_writer_split_wim_under_4gb(self):
        from linux_rufus.core.writers.windows_writer import WindowsWriter

        sources_dir = os.path.join(self.temp_dir, "sources")
        os.makedirs(sources_dir, exist_ok=True)
        wim_path = os.path.join(sources_dir, "install.wim")

        # Create small fake WIM file (1 KB)
        with open(wim_path, "wb") as f:
            f.write(b"SMALL_WIM")

        # Should not split because it's under 4GB
        result = WindowsWriter.split_wim_if_needed(self.temp_dir)
        self.assertFalse(result)
        self.assertTrue(os.path.exists(wim_path))

    def test_windows_writer_bypass_injection(self):
        from linux_rufus.core.writers.windows_writer import WindowsWriter

        sources_dir = os.path.join(self.temp_dir, "sources")
        os.makedirs(sources_dir, exist_ok=True)

        writer = WindowsWriter(
            source_path="fake.iso",
            target_device="/dev/null",
            bypass_tpm=True,
            bypass_ram=True,
            bypass_secure_boot=True,
        )
        writer.apply_windows_tweaks(self.temp_dir)

        reg_file = os.path.join(sources_dir, "rufus_bypass.reg")
        self.assertTrue(os.path.exists(reg_file))
        with open(reg_file, "r") as f:
            content = f.read()
            self.assertIn("BypassTPMCheck", content)
            self.assertIn("BypassSecureBootCheck", content)
            self.assertIn("BypassRAMCheck", content)


if __name__ == "__main__":
    unittest.main()
