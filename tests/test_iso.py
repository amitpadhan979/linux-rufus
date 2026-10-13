"""
Unit tests for ISOInspector and image classification.
"""

import os
import tempfile
import unittest

from linux_rufus.core.iso import ISOInspector, ISOInfo


class TestISOInspector(unittest.TestCase):
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

    def test_small_file_detection(self):
        tiny_file = os.path.join(self.temp_dir, "tiny.iso")
        with open(tiny_file, "wb") as f:
            f.write(b"NOT_AN_ISO")

        inspector = ISOInspector(tiny_file)
        info = inspector.inspect()
        self.assertFalse(info.is_iso)
        self.assertEqual(info.file_size, len(b"NOT_AN_ISO"))

    def test_synthetic_iso9660_hybrid(self):
        iso_file = os.path.join(self.temp_dir, "test_hybrid.iso")
        # Build synthetic hybrid ISO:
        # 1. Sector 0 (512 bytes): MBR with 0x55AA signature and dummy partition entry
        mbr = bytearray(512)
        mbr[510:512] = b"\x55\xaa"
        mbr[0x1BE + 4] = 0x83  # Linux native partition
        
        # 2. Sector 16 (offset 32768): ISO9660 PVD
        pvd = bytearray(2048)
        pvd[0] = 1
        pvd[1:6] = b"CD001"
        label = "TEST_UBUNTU_2404".ljust(32).encode("utf-8")
        pvd[40:72] = label

        total_size = 32768 + 2048 + 4096
        with open(iso_file, "wb") as f:
            f.write(mbr)
            f.write(b"\x00" * (32768 - 512))
            f.write(pvd)
            f.write(b"\x00" * 4096)

        inspector = ISOInspector(iso_file)
        info = inspector.inspect()

        self.assertTrue(info.is_iso)
        self.assertTrue(info.is_hybrid)
        self.assertEqual(info.volume_id, "TEST_UBUNTU_2404")
        self.assertEqual(info.recommended_mode, "raw")

    def test_synthetic_windows_iso(self):
        win_iso = os.path.join(self.temp_dir, "win11.iso")
        total_size = 32768 + 2048 + 4096
        
        pvd = bytearray(2048)
        pvd[0] = 1
        pvd[1:6] = b"CD001"
        pvd[40:72] = "CCCOMA_X64FRE_EN-US_DV9".ljust(32).encode("utf-8")

        with open(win_iso, "wb") as f:
            # MBR with INSTALL.WIM marker
            f.write(b"INSTALL.WIM" + b"\x00" * (32768 - 11))
            f.write(pvd)
            f.write(b"\x00" * 4096)

        inspector = ISOInspector(win_iso)
        info = inspector.inspect()

        self.assertTrue(info.is_windows)
        self.assertEqual(info.recommended_mode, "partition")
        self.assertEqual(info.recommended_partition_scheme, "GPT")

    def test_compute_hashes(self):
        sample = os.path.join(self.temp_dir, "hash_sample.bin")
        payload = b"TEST_PAYLOAD_FOR_HASH"
        with open(sample, "wb") as f:
            f.write(payload)

        inspector = ISOInspector(sample)
        sha256_val, md5_val = inspector.compute_hashes()

        import hashlib
        self.assertEqual(sha256_val, hashlib.sha256(payload).hexdigest())
        self.assertEqual(md5_val, hashlib.md5(payload).hexdigest())

        info = inspector.inspect(compute_hash=True)
        self.assertEqual(info.sha256, sha256_val)
        self.assertEqual(info.md5, md5_val)


if __name__ == "__main__":
    unittest.main()
