"""Qt-independent Codegen、Build 與 Flash operation API。"""

import importlib
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

import gen_cnn_lib


__all__ = [
    "CodegenConfig",
    "BuildConfig",
    "FlashConfig",
    "ToolOperationResult",
    "codegen_run_from_config",
    "build_run_from_config",
    "flash_run_from_config",
    "process_run_streamed",
]


@dataclass
class CodegenConfig:
    """固定的 MCU CNN library generation 輸入。"""

    metadata_path: str
    model_path: str
    output_dir: str
    base_name: str = "cnn"
    std_base_a: list[int] = field(default_factory=list)
    std_hold_a: list[int] = field(default_factory=list)
    data_dir: str = ""
    alpha: float = 0.20
    margin: float = 0.45
    exit_thresh: float = 0.25
    infer_stride: int = 6
    slope_factor: float = 20.0
    tier_data: dict = field(default_factory=dict)

    @property
    def meta_path(self) -> str:
        """保留舊 caller 的唯讀欄位名稱。"""
        return self.metadata_path

    @property
    def outdir(self) -> str:
        """保留舊 caller 的唯讀欄位名稱。"""
        return self.output_dir


@dataclass
class BuildConfig:
    """固定的 firmware build 輸入。"""

    project_dir: str
    build_tool_dir: str
    config_name: str = "Debug"
    do_clean: bool = False
    target_name: str = "glove_ml_mlp"

    @property
    def proj_dir(self) -> str:
        """保留舊 caller 的唯讀欄位名稱。"""
        return self.project_dir


@dataclass
class FlashConfig:
    """固定的 firmware image 與 serial device 輸入。"""

    srec_path: str
    serial_port: str
    tool_dir: str

    @property
    def com_port(self) -> str:
        """保留舊 caller 的唯讀欄位名稱。"""
        return self.serial_port


@dataclass(frozen=True)
class ToolOperationResult:
    """Codegen、Build 與 Flash 共用的終止狀態。"""

    status: str
    return_code: Optional[int] = None
    message: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


def codegen_run_from_config(
    config: CodegenConfig,
    log_fn: Optional[Callable[[str], None]] = None,
) -> ToolOperationResult:
    """依固定 Config 產生 MCU CNN library，並回傳標準 operation result。"""

    effective_log_fn = log_fn or print
    post_config = {
        "alpha": config.alpha,
        "margin": config.margin,
        "exit_thresh": config.exit_thresh,
        "infer_stride": config.infer_stride,
        "slope_factor": config.slope_factor,
        "thresh_entry": config.tier_data.get("thresh_entry", 0.50),
        "stable_fast": config.tier_data.get("stable_fast", 0),
        "stable_normal": config.tier_data.get("stable_normal", 10),
        "stable_restricted": config.tier_data.get("stable_restricted", 20),
        "thresh_priority": config.tier_data.get("thresh_priority", 0.70),
        "thresh_restricted": config.tier_data.get("thresh_restricted", 0.75),
        "priority_ids": config.tier_data.get("priority_ids", []),
        "restricted_ids": config.tier_data.get("restricted_ids", []),
    }

    # 開發期間可能直接修改 generator；每次執行前 reload，讓 UI 不必重啟。
    importlib.reload(gen_cnn_lib)
    generated_result = gen_cnn_lib.generate_cnn_lib(
        meta_path=config.metadata_path,
        model_path=config.model_path,
        out_dir=config.output_dir,
        std_base_a=config.std_base_a,
        std_hold_a=config.std_hold_a,
        tflite_path=None,
        data_dir=config.data_dir,
        log_fn=effective_log_fn,
        post_cfg=post_config,
    )
    if not generated_result:
        return ToolOperationResult(status="failed", message="Generation failed (check log)")

    payload = {"output_dir": config.output_dir}
    if isinstance(generated_result, dict):
        payload.update(generated_result)
    return ToolOperationResult(status="completed", payload=payload)


def _process_terminate_and_wait(
    process: subprocess.Popen,
    timeout_seconds: float = 5.0,
) -> int:
    """終止 child process，並確保 OS process handle 被回收。"""

    if process.poll() is not None:
        return int(process.returncode)
    process.terminate()
    try:
        return int(process.wait(timeout=timeout_seconds))
    except subprocess.TimeoutExpired:
        # 部分燒錄工具會忽略 terminate；kill 是避免 process 洩漏的有界 fallback。
        process.kill()
        return int(process.wait(timeout=timeout_seconds))


def process_run_streamed(
    command: Sequence[str],
    log_fn: Callable[[str], None],
    stop_event=None,
    cwd: Optional[str] = None,
    encoding: Optional[str] = None,
    retry_patterns: Sequence[str] = (),
) -> ToolOperationResult:
    """執行外部工具、串流 output，並回傳明確的終止狀態。"""

    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=encoding,
        errors="replace",
        bufsize=1,
        cwd=cwd,
    )
    output_queue = queue.Queue()

    def _process_read_output() -> None:
        if process.stdout is not None:
            for output_line in iter(process.stdout.readline, ""):
                output_queue.put(output_line)
        output_queue.put(None)

    # Helper thread 避免外部工具長時間無 output 時阻塞取消流程。
    output_thread = threading.Thread(target=_process_read_output, daemon=True)
    output_thread.start()
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                return_code = _process_terminate_and_wait(process)
                return ToolOperationResult(
                    status="cancelled",
                    return_code=return_code,
                    message="Operation cancelled by user.",
                )
            try:
                output = output_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if output is None:
                break
            line = output.strip()
            if line:
                log_fn(line)
            matching_pattern = next(
                (pattern for pattern in retry_patterns if pattern in line),
                None,
            )
            if matching_pattern is not None:
                return_code = _process_terminate_and_wait(process)
                return ToolOperationResult(
                    status="retry_requested",
                    return_code=return_code,
                    message="Device not responding",
                )

        return_code = int(process.wait())
        status = "completed" if return_code == 0 else "failed"
        return ToolOperationResult(status=status, return_code=return_code)
    finally:
        if process.poll() is None:
            _process_terminate_and_wait(process)
        if process.stdout is not None:
            process.stdout.close()
        output_thread.join(timeout=1.0)


def build_run_from_config(
    config: BuildConfig,
    log_fn: Callable[[str], None],
    stop_event=None,
) -> ToolOperationResult:
    """執行 firmware build，並回傳共用 lifecycle state。"""

    build_script = Path(config.build_tool_dir) / "build_glove_debug.bat"
    if not build_script.exists():
        raise RuntimeError(f"Build script not found: {build_script}")
    command = [str(build_script), config.project_dir, config.config_name]
    if config.do_clean:
        command.append("clean")
    command.append(config.target_name)
    log_fn(f"Executing: {' '.join(command)}")
    log_fn(f"Target: {config.target_name}")
    return process_run_streamed(
        command,
        log_fn=log_fn,
        stop_event=stop_event,
        cwd=str(config.build_tool_dir),
        encoding="utf-8",
    )


def flash_run_from_config(
    config: FlashConfig,
    log_fn: Callable[[str], None],
    stop_event=None,
) -> ToolOperationResult:
    """執行 firmware flash，並區分完成、取消、失敗或 retry。"""

    tool_dir = Path(config.tool_dir)
    candidates = (
        tool_dir / "flashtool" / "flash.bat",
        tool_dir.parent / "flashtool" / "flash.bat",
        Path(__file__).parent / "flashtool" / "flash.bat",
    )
    flash_script = next((path for path in candidates if path.exists()), None)
    if flash_script is None:
        raise RuntimeError("Flash script 'flashtool/flash.bat' not found.")
    command = [str(flash_script), config.srec_path, config.serial_port]
    log_fn(f"Executing: {' '.join(command)}")
    return process_run_streamed(
        command,
        log_fn=log_fn,
        stop_event=stop_event,
        retry_patterns=("E3000105", "device is not responding"),
    )
