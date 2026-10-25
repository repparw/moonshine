"""Tests for the bounded model, including a deliberately broken transition."""

import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).with_name("inflight_model.py")
spec = importlib.util.spec_from_file_location("inflight_model", path)
model = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = model
spec.loader.exec_module(model)


class InFlightOwnershipTests(unittest.TestCase):
    def test_all_interleavings_hold_invariants(self):
        for bound in (1, 2, 3):
            with self.subTest(frames=bound):
                visited, failure = model.explore(max_frames=bound)
                self.assertGreater(len(visited), bound)
                self.assertIsNone(failure)

    def test_mutation_of_rejected_send_finds_counterexample(self):
        visited, failure = model.explore(max_frames=2, broken_rejection=True)
        self.assertGreater(len(visited), 0)
        self.assertIsNotNone(failure)
        trace, reason, _ = failure
        self.assertTrue(any(step.startswith("send rejected") for step in trace))
        self.assertIn("count", reason)

    def test_no_double_release_is_reachable(self):
        state = model.State(
            owners=((0, "released"),), count=0,
            sender_open=False, receiver_open=False, next_frame=1, releases=1,
        )
        self.assertEqual(list(model.successors(state)), [])
        self.assertIsNone(model.invariant(state))


if __name__ == "__main__":
    unittest.main()
