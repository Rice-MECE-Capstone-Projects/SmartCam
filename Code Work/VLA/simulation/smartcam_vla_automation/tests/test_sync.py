#!/usr/bin/env python3
"""Minimal pure-python unit tests for timestamp matching and image handling."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_raw import latest_before, image_as_ppm


class FakeImage:
    encoding = "bgr8"
    height = 1
    width = 2
    step = 8
    data = bytes([10, 20, 30, 40, 50, 60, 0, 0])


class TestExport(unittest.TestCase):
    def test_latest_asof_alignment(self):
        ts = [100, 200, 350]
        vals = ["a", "b", "c"]
        self.assertEqual(latest_before(ts, vals, 210, 25), "b")
        self.assertIsNone(latest_before(ts, vals, 210, 5))
        self.assertEqual(latest_before(ts, vals, 200, 2), "b")
        self.assertIsNone(latest_before(ts, vals, 99, 200))

    def test_image_stride_bgr_to_rgb(self):
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy not installed")
        ppm = image_as_ppm(FakeImage())
        self.assertTrue(ppm.startswith(b"P6\n2 1\n255\n"))
        self.assertEqual(ppm.split(b"255\n", 1)[1], bytes([30, 20, 10, 60, 50, 40]))


if __name__ == "__main__":
    unittest.main()
