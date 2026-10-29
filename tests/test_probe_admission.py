"""Unknown IO evidence must survive bounded threads and stay request-local."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import unittest

from tests.test_xsm import TempState


class AdmissionProbeEvidenceTests(TempState):
    def test_real_io_error_is_observed_through_worker_and_is_not_a_negative_value(self):
        from xsm import probe
        missing = Path(self.tmp) / "unavailable-file"
        unreadable = Path(self.tmp) / "not-a-regular-file"
        unreadable.mkdir()
        with probe.observe_unavailable() as error:
            self.assertIsNone(probe.bounded(unreadable.read_bytes))
        self.assertTrue(error["unavailable"])
        with probe.observe_unavailable() as known_absence:
            self.assertIsNone(probe.bounded(missing.read_bytes))
        self.assertFalse(known_absence["unavailable"])
        with probe.observe_unavailable() as valid_negative:
            self.assertIsNone(probe.bounded(lambda: None))
        self.assertFalse(valid_negative["unavailable"])

    def test_parallel_positive_read_does_not_inherit_another_requests_io_error(self):
        from xsm import probe
        available = Path(self.tmp) / "available-file"
        available.write_bytes(b"current native evidence")
        unreadable = Path(self.tmp) / "not-a-regular-file"
        unreadable.mkdir()
        barrier = threading.Barrier(2)

        def read(path):
            with probe.observe_unavailable() as observed:
                barrier.wait(timeout=3)
                value = probe.bounded(path.read_bytes)
                return value, observed["unavailable"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            positive = executor.submit(read, available)
            negative = executor.submit(read, unreadable)
            self.assertEqual(positive.result(timeout=5), (b"current native evidence", False))
            self.assertEqual(negative.result(timeout=5), (None, True))
        with probe.observe_unavailable() as next_request:
            self.assertEqual(probe.bounded(available.read_bytes), b"current native evidence")
        self.assertFalse(next_request["unavailable"])
