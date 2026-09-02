"""Training common API contract tests using the default configuration."""

import unittest
from unittest.mock import patch

import training_api
import training_cnn
import training_contracts
import training_ds_tcn
import training_validation


class TrainingApiTest(unittest.TestCase):
    """驗證 UI 以外的 caller 可安全使用 Training common API。"""

    def setUp(self):
        # 每個案例重新建立 Config，避免測試之間共享可變欄位。
        self.config = training_api.TrainingConfig()

    def test_default_config_values(self):
        self.assertEqual(self.config.data_dir, ".")
        self.assertEqual(self.config.channels, None)
        self.assertEqual(self.config.ch_list, [1, 2, 3, 4, 5])
        self.assertEqual(self.config.window_len, 40)
        self.assertEqual(self.config.window_step, 2)
        self.assertEqual(self.config.batch_size, 32)
        self.assertEqual(self.config.epochs, 200)
        self.assertEqual(self.config.output_model_path, "gesture_model_cnn_v1.h5")
        self.assertEqual(self.config.output_metadata_path, "gesture_model_meta_cnn_v1.pkl")

    def test_all_trainers_share_the_api_config_class(self):
        self.assertIs(training_cnn.TrainingConfig, training_api.TrainingConfig)
        self.assertIs(training_ds_tcn.TrainingConfig, training_api.TrainingConfig)
        self.assertIs(training_cnn.TrainCfg, training_api.TrainingConfig)
        self.assertIs(training_ds_tcn.TrainCfg, training_api.TrainingConfig)

    def test_default_config_validation_reports_missing_labels(self):
        issues = training_validation.training_validate_config(self.config)
        self.assertEqual(
            [issue.code for issue in issues],
            [training_validation.TRAINING_ISSUE_LABELS_EMPTY],
        )

    def test_default_config_routes_to_cnn_and_normalizes_result(self):
        raw_result = {
            "model_path": "trained.keras",
            "metadata_path": "trained.pkl",
            "report_path": "training_report.png",
            "report": {
                "accuracy": 0.91,
                "macro avg": {
                    "precision": 0.81,
                    "recall": 0.82,
                    "f1-score": 0.83,
                },
            },
            "validation_accuracy": 0.90,
            "training_time_seconds": 12.5,
        }
        progress_fn = lambda progress: None

        with patch("training_cnn.training_run_cnn", return_value=raw_result) as run_cnn:
            result = training_api.training_run_from_config(
                self.config,
                progress_fn=progress_fn,
            )

        self.assertIs(run_cnn.call_args.args[0], self.config)
        self.assertIs(run_cnn.call_args.kwargs["progress_fn"], progress_fn)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.backbone, "cnn")
        self.assertEqual(result.model_path, "trained.keras")
        self.assertEqual(result.metadata_path, "trained.pkl")
        self.assertEqual(result.top_1_accuracy, 0.91)
        self.assertEqual(result.f1_score, 0.83)
        self.assertEqual(result.validation_accuracy, 0.90)
        self.assertEqual(result.training_time_seconds, 12.5)

    def test_default_config_routes_to_ds_tcn(self):
        raw_result = {
            "model_path": "trained.keras",
            "metadata_path": "trained.pkl",
            "report": {},
        }

        with patch(
            "training_ds_tcn.training_run_ds_tcn",
            return_value=raw_result,
        ) as run_ds_tcn:
            result = training_api.training_run_from_config(
                self.config,
                backbone="ds_tcn",
            )

        self.assertIs(run_ds_tcn.call_args.args[0], self.config)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.backbone, "ds_tcn")

    def test_cancelled_training_returns_cancelled_result(self):
        with patch(
            "training_cnn.training_run_cnn",
            side_effect=training_contracts.TrainingCancelledError("cancelled for test"),
        ):
            result = training_api.training_run_from_config(self.config)

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.backbone, "cnn")
        self.assertEqual(result.message, "cancelled for test")
        self.assertIsNone(result.model_path)
        self.assertIsNone(result.metadata_path)

    def test_progress_callback_emits_training_progress(self):
        log_messages = []
        progress_updates = []

        def receive_progress(progress):
            # 測試時保留肉眼可讀輸出，同時收集物件供 assertion 驗證。
            print(f"progress_fn: {progress.to_dict()}")
            progress_updates.append(progress)

        callback = training_cnn.UIProgressCallback(
            log_messages.append,
            total_epochs=200,
            progress_fn=receive_progress,
        )

        callback.on_epoch_end(0, {
            "loss": 0.80,
            "accuracy": 0.60,
            "val_loss": 0.70,
            "val_accuracy": 0.65,
        })

        self.assertEqual(len(log_messages), 1)
        self.assertEqual(progress_updates, [
            training_contracts.TrainingProgress(
                epoch=1,
                total_epochs=200,
                loss=0.80,
                accuracy=0.60,
                validation_loss=0.70,
                validation_accuracy=0.65,
            )
        ])


if __name__ == "__main__":
    unittest.main()
