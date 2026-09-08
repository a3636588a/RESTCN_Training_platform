"""Public-boundary checks for the UI-independent TinyOL API."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tinyol_api


class TinyOlApiTests(unittest.TestCase):
    def _record_config(self, **overrides):
        values = {
            "serial_port": "COM6",
            "baud": 921600,
            "output_dir": "tinyol-output",
            "session_id": "tinyol_test",
            "segment_index": 1,
            "target_id": 2,
            "target_name": "gesture-2",
            "record_samples": 150,
            "start_offset": 30,
            "window_len": 35,
            "channels": [1, 2, 3, 4, 5],
            "use_manual_holdavg": True,
            "manual_holdavg": {},
            "std_baseline_a": {},
            "std_holdavg_a": {},
        }
        values.update(overrides)
        return tinyol_api.TinyOlRecordConfig(**values)

    def test_default_record_config_is_valid(self):
        self.assertEqual(tinyol_api.tinyol_validate_record_config(self._record_config()), [])

    def test_record_samples_must_cover_window(self):
        issues = tinyol_api.tinyol_validate_record_config(
            self._record_config(record_samples=64, start_offset=30, window_len=35)
        )
        self.assertIn("record_samples must be >= start_offset + window_len (65)", issues)

    def test_public_exports_are_stable(self):
        self.assertEqual(
            set(tinyol_api.__all__),
            {
                "TinyOlCancelledError",
                "TinyOlRecordConfig",
                "TinyOlTrainConfig",
                "tinyol_record_from_config",
                "tinyol_train_from_config",
                "tinyol_validate_record_config",
            },
        )


if __name__ == "__main__":
    unittest.main()
