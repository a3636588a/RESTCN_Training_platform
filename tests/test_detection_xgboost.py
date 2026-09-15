"""XGBoost detector feature-alignment tests."""

import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from xgboost_detection_model import XGBoostRealtimeGestureDetector
from training_xgboost import build_signal, extract_40_features


class XGBoostFeatureAlignmentTest(unittest.TestCase):
    def test_detect_feature_builder_matches_training(self):
        window_d = np.arange(250, dtype=np.float32).reshape(50, 5)

        expected = extract_40_features(window_d)
        actual = XGBoostRealtimeGestureDetector.extract_40_features(window_d)

        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.shape, (40,))

    def test_feature_builder_accepts_configured_window_length(self):
        window_d = np.arange(175, dtype=np.float32).reshape(35, 5)

        features = XGBoostRealtimeGestureDetector.extract_40_features(window_d)

        self.assertEqual(features.shape, (40,))

    def test_dn_uses_holdavg_span(self):
        row = np.array([[120.0, 160.0]], dtype=np.float32)
        base = np.array([[100.0, 100.0]], dtype=np.float32)
        hold = np.array([[200.0, 300.0]], dtype=np.float32)

        dn = build_signal(row, base, hold, "dn")

        np.testing.assert_array_equal(dn, np.array([[0.2, 0.3]], dtype=np.float32))

    def test_dn_augmentation_changes_delta_and_span(self):
        row = np.array([[120.0]], dtype=np.float32)
        base = np.array([[100.0]], dtype=np.float32)
        hold = np.array([[200.0]], dtype=np.float32)

        dn = build_signal(
            row, base, hold, "dn",
            delta_gain=2.0,
            span_gain=2.0,
            delta_offset=10.0,
        )

        np.testing.assert_array_equal(dn, np.array([[0.25]], dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
