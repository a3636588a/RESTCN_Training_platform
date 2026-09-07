"""Detection inference stride ownership tests."""

import sys
import unittest
from pathlib import Path

# 支援直接執行此測試檔，也避免載入 tests 目錄中的同名 module。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import detection_api
from detection_contracts import ModelPrediction


class _FakeDetector:
    """只記錄 API 呼叫次數，不在 Model 內實作第二套 stride。"""

    channels = [1]
    id_to_name = {0: "zero"}
    clf = None

    def __init__(self):
        self.predict_calls = 0

    def push_data(self, row_map, base_map, hold_map, gain_map):
        pass

    def predict(self, gain_map):
        self.predict_calls += 1
        return ModelPrediction(pred_id=0, confidence=1.0, probabilities=(1.0,))


def _build_config(infer_stride: int) -> detection_api.DetectionConfig:
    return detection_api.DetectionConfig(
        serial_port="COM1",
        baud=921600,
        model_path="model.keras",
        metadata_path="metadata.pkl",
        post_alpha=0.2,
        post_margin=0.45,
        post_tier_data={},
        post_exit_thresh=0.25,
        post_slope_factor=20.0,
        infer_stride=infer_stride,
        print_proba=False,
        use_manual_holdavg=False,
        manual_holdavg={},
        enable_gain_map=False,
        std_baseline_a={},
        std_holdavg_a={},
        min_span_b=1.0,
        gain_clamp_min=0.5,
        gain_clamp_max=2.0,
    )


class DetectionStrideTest(unittest.TestCase):
    def _build_session(self, infer_stride: int):
        detector = _FakeDetector()
        session = detection_api._DetectionSession(
            config=_build_config(infer_stride),
            detector=detector,
            dynamic_gestures=[],
            runtime_state=detection_api.DetectionRuntimeState(gain_map={1: 1.0}),
            log_fn=lambda message: None,
        )
        return detector, session

    def test_uart_stride_is_applied_once_by_api(self):
        detector, session = self._build_session(infer_stride=3)

        updates = [
            session.process_sample(
                row_map={1: index},
                base_map={1: 0},
                hold_map={1: 100},
                timestamp=float(index),
                apply_config_stride=True,
            )
            for index in range(1, 7)
        ]

        self.assertEqual(detector.predict_calls, 2)
        self.assertEqual(sum(update is not None for update in updates), 2)

    def test_csv_path_can_request_every_sample(self):
        detector, session = self._build_session(infer_stride=3)

        for index in range(1, 7):
            session.process_sample(
                row_map={1: index},
                base_map={1: 0},
                hold_map={1: 100},
                timestamp=float(index),
                apply_config_stride=False,
            )

        self.assertEqual(detector.predict_calls, 6)


if __name__ == "__main__":
    unittest.main()
