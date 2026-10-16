"""XGBoost detector feature-alignment tests."""

import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from xgboost_detection_model import XGBoostRealtimeGestureDetector
from training_xgboost import build_signal, extract_40_features, extract_features, make_feature_names


class XGBoostFeatureAlignmentTest(unittest.TestCase):
    def test_onset60_v2_relaxes_only_stable_prefix(self):
        w = np.zeros((50, 5))
        w[:5, :] = np.array([0., .015, .03, .045, .06])[:, None]
        w[5:, :] = .03
        w[20:, :] = .3
        old = extract_features(w, 'onset60')
        new = extract_features(w, 'onset60_v2')
        np.testing.assert_array_equal(old[40:45], -np.ones(5))
        np.testing.assert_array_equal(new[40:45], np.ones(5))
        np.testing.assert_allclose(new[45:50], np.full(5,20/49))
        np.testing.assert_array_equal(new[:40], old[:40])
        self.assertEqual(len(make_feature_names(range(1,6),'onset60_v2')),60)
        np.testing.assert_array_equal(new, XGBoostRealtimeGestureDetector.extract_features(w,'onset60_v2'))
        w[:5, :] *= 2  # > .08 still unknown
        np.testing.assert_array_equal(extract_features(w,'onset60_v2')[40:45],-np.ones(5))

    def test_onset60_relative_order_offset_and_noise(self):
        w = np.tile([.3, .6, .2, .8, .1], (50, 1))
        w[12:, 0] += .1
        w[20:, 1] += .1
        w[12:, 2] += .1
        w[25:27, 3] += .2  # spike, not sustained
        f = extract_features(w, 'onset60')
        self.assertEqual(f.shape, (60,))
        self.assertEqual(len(make_feature_names(range(1,6),'onset60')),60)
        np.testing.assert_array_equal(f[:40], extract_40_features(w))
        np.testing.assert_array_equal(f, XGBoostRealtimeGestureDetector.extract_features(w,'onset60'))
        np.testing.assert_array_equal(f[40:45], [1,1,1,0,0])
        np.testing.assert_allclose(f[45:48], np.array([12,20,12])/49)
        self.assertAlmostEqual(float(f[50]),8/49,places=6)
        np.testing.assert_allclose(f[40:], extract_features(w+1,'onset60')[40:])

    def test_onset60_unstable_prefix_and_short_input(self):
        w = np.tile(np.linspace(0,1,50)[:,None], (1,5))
        f = extract_features(w,'onset60')
        np.testing.assert_array_equal(f[40:45], -np.ones(5))
        for n in (8,35,50):
            f=extract_features(np.ones((n,5)),'onset60')
            np.testing.assert_array_equal(f[40:45],np.zeros(5))
            self.assertTrue(np.isfinite(f).all())
        with self.assertRaisesRegex(ValueError,'window_len'):
            extract_features(np.zeros((7,5)),'onset60')

    def test_onset95_order_and_censored_channels(self):
        w = np.zeros((50, 5), dtype=np.float32)
        w[8:, 0] = .2
        w[17:, 1] = .2
        w[8:, 2] = .2
        w[:, 3] = .2
        w[6:8, 4] = .2  # two-tick noise must not count
        f = extract_features(w, 'onset95')
        self.assertEqual(f.shape, (95,))
        names = make_feature_names(range(1, 6), 'onset95')
        self.assertEqual(len(names), 95)
        np.testing.assert_array_equal(f, XGBoostRealtimeGestureDetector.extract_features(w, 'onset95'))
        np.testing.assert_array_equal(f[75:80], [1, 1, 1, -1, 0])
        self.assertAlmostEqual(float(f[names.index('onset_lag_ch2_minus_ch1')]), 9/49, places=6)
        self.assertEqual(f[names.index('onset_lag_ch3_minus_ch1')], 0)
        self.assertEqual(f[names.index('onset_lag_ch4_minus_ch1')], -2)
        reverse = extract_features(w[:, [1, 0, 2, 3, 4]], 'onset95')
        self.assertAlmostEqual(float(reverse[85]), -9/49, places=6)

    def test_onset95_truncated_end_is_not_confirmed(self):
        w = np.zeros((50, 5), dtype=np.float32)
        w[-2:, :] = .2
        f = extract_features(w, 'onset95')
        np.testing.assert_array_equal(f[75:80], np.zeros(5))
        np.testing.assert_array_equal(f[80:85], -np.ones(5))

    def test_motion75_periodic_signal_and_static_prefix(self):
        t = np.arange(50)
        window = np.tile((2 + np.sin(2*np.pi*t/10))[:, None], (1, 5))
        features = extract_features(window, 'motion75')
        self.assertEqual(features.shape, (75,))
        self.assertEqual(len(make_feature_names(range(1, 6), 'motion75')), 75)
        np.testing.assert_array_equal(features[:40], extract_40_features(window))
        np.testing.assert_array_equal(features, XGBoostRealtimeGestureDetector.extract_features(window, 'motion75'))
        np.testing.assert_allclose(features[65:70], -1, atol=1e-6)
        np.testing.assert_allclose(features[70:75], 1, atol=1e-6)

    def test_motion75_constant_zero_and_short_windows(self):
        for length in (12, 35, 50):
            for level in (0., 2.):
                features = extract_features(np.full((length, 5), level), 'motion75')
                self.assertTrue(np.isfinite(features).all())
                np.testing.assert_array_equal(features[40:], np.zeros(35))
        with self.assertRaisesRegex(ValueError, 'window_len'):
            extract_features(np.zeros((11, 5)), 'motion75')

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

    def test_time140_feature_builder_matches_training(self):
        window_d = np.arange(250, dtype=np.float32).reshape(50, 5)

        expected = extract_features(window_d, "time140")
        actual = XGBoostRealtimeGestureDetector.extract_features(window_d, "time140")

        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.shape, (140,))

    def test_wave215_feature_builder_matches_training(self):
        window_d = np.arange(250, dtype=np.float32).reshape(50, 5)

        expected = extract_features(window_d, "wave215")
        actual = XGBoostRealtimeGestureDetector.extract_features(window_d, "wave215")

        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.shape, (215,))

    def test_hybrid225_feature_builder_matches_training(self):
        window_d = np.arange(250, dtype=np.float32).reshape(50, 5)

        expected = extract_features(window_d, "hybrid225")
        actual = XGBoostRealtimeGestureDetector.extract_features(window_d, "hybrid225")

        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.shape, (225,))

    def test_feature_name_counts_match_feature_sets(self):
        self.assertEqual(len(make_feature_names([1, 2, 3, 4, 5], "stats40")), 40)
        self.assertEqual(len(make_feature_names([1, 2, 3, 4, 5], "time140")), 140)
        self.assertEqual(len(make_feature_names([1, 2, 3, 4, 5], "wave215")), 215)
        self.assertEqual(len(make_feature_names([1, 2, 3, 4, 5], "hybrid225")), 225)

    def test_dn_uses_holdavg_span(self):
        row = np.array([[120.0, 160.0]], dtype=np.float32)
        base = np.array([[100.0, 100.0]], dtype=np.float32)
        hold = np.array([[200.0, 300.0]], dtype=np.float32)

        dn = build_signal(row, base, hold, "dn")

        np.testing.assert_array_equal(dn, np.array([[0.2, 0.3]], dtype=np.float32))

    def test_clip_zero_removes_negative_delta_before_dn(self):
        row = np.array([[80.0, 120.0]], dtype=np.float32)
        base = np.array([[100.0, 100.0]], dtype=np.float32)
        hold = np.array([[200.0, 200.0]], dtype=np.float32)

        dn = build_signal(row, base, hold, "dn", negative_delta_mode="clip_zero")

        np.testing.assert_array_equal(dn, np.array([[0.0, 0.2]], dtype=np.float32))

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
