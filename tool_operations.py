"""UI-independent codegen, build, and flash operation boundaries."""

import importlib
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

import gen_cnn_lib


@dataclass(frozen=True)
class ToolOperationResult:
    """Stable terminal state returned by external tool operations."""

    status: str
    return_code: Optional[int] = None
    message: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


def _process_terminate_and_wait(process: subprocess.Popen, timeout_seconds: float = 5.0) -> int:
    """Terminate a child and guarantee that its OS process handle is reaped."""

    if process.poll() is not None:
        return int(process.returncode)

    process.terminate()
    try:
        return int(process.wait(timeout=timeout_seconds))
    except subprocess.TimeoutExpired:
        # Some vendor tools ignore terminate while programming hardware. Kill is
        # the bounded fallback that prevents a cancelled worker leaking a process.
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
    """Run one process, stream output, and return one explicit terminal state."""

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

    # Reading stdout on a helper thread keeps cancellation responsive when a
    # vendor tool remains silent for a long operation.
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
            matching_pattern = next((pattern for pattern in retry_patterns if pattern in line), None)
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
        # Exceptions from logging or result handling must not orphan a child.
        if process.poll() is None:
            _process_terminate_and_wait(process)
        if process.stdout is not None:
            process.stdout.close()
        output_thread.join(timeout=1.0)


def codegen_run_from_config(config, log_fn: Optional[Callable[[str], None]] = None) -> ToolOperationResult:
    """Generate the CNN library without depending on Qt worker state."""

    effective_log_fn = log_fn or print
    post_config = {
        "alpha": config.alpha,
        "margin": config.margin,
        # Keep the generated MCU latch-release behavior aligned with PC Detect.
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

    # Preserve the original development workflow where codegen edits made in a
    # running UI session are picked up without restarting the application.
    importlib.reload(gen_cnn_lib)
    generated_result = gen_cnn_lib.generate_cnn_lib(
        meta_path=config.meta_path,
        model_path=config.model_path,
        out_dir=config.outdir,
        std_base_a=config.std_base_a,
        std_hold_a=config.std_hold_a,
        tflite_path=None,
        data_dir=config.data_dir,
        log_fn=effective_log_fn,
        post_cfg=post_config,
    )
    if not generated_result:
        return ToolOperationResult(status="failed", message="Generation failed (check log)")

    payload = {"out_dir": config.outdir}
    if isinstance(generated_result, dict):
        payload.update(generated_result)
    return ToolOperationResult(status="completed", payload=payload)


def build_run_from_config(config, log_fn: Callable[[str], None], stop_event=None) -> ToolOperationResult:
    """Run the configured firmware build and return its lifecycle state."""

    build_script = Path(config.build_tool_dir) / "build_glove_debug.bat"
    if not build_script.exists():
        raise RuntimeError(f"Build script not found: {build_script}")

    command = [str(build_script), config.proj_dir, config.config_name]
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


def flash_run_from_config(config, log_fn: Callable[[str], None], stop_event=None) -> ToolOperationResult:
    """Run the flash tool and classify success, cancellation, failure, or retry."""

    tool_dir = Path(config.tool_dir)
    candidates = (
        tool_dir / "flashtool" / "flash.bat",
        tool_dir.parent / "flashtool" / "flash.bat",
        Path(__file__).parent / "flashtool" / "flash.bat",
    )
    flash_script = next((path for path in candidates if path.exists()), None)
    if flash_script is None:
        raise RuntimeError("Flash script 'flashtool/flash.bat' not found.")

    command = [str(flash_script), config.srec_path, config.com_port]
    log_fn(f"Executing: {' '.join(command)}")
    return process_run_streamed(
        command,
        log_fn=log_fn,
        stop_event=stop_event,
        retry_patterns=("E3000105", "device is not responding"),
    )
