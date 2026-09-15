"""XGBoost detector feature-alignment tests."""

import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from xgboost_detection_model import XGBoostRealtimeGestureDetector
from training_xgboost import extract_40_features


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


if __name__ == "__main__":
    unittest.main()
