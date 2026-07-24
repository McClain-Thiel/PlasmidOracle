from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    runtime_seconds: float


class CommandFailedError(RuntimeError):
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        command = " ".join(result.argv)
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        super().__init__(f"Command failed with exit code {result.returncode}: {command}\n{detail}")


class CommandTimeoutError(TimeoutError):
    def __init__(self, argv: Sequence[str], timeout_seconds: float) -> None:
        self.argv = tuple(argv)
        self.timeout_seconds = timeout_seconds
        command = " ".join(self.argv)
        super().__init__(f"Command exceeded {timeout_seconds:g}s timeout: {command}")


class ProcessRunner(Protocol):
    def run(
        self,
        argv: Sequence[str | os.PathLike[str]],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
        check: bool = True,
    ) -> ProcessResult: ...


@dataclass(frozen=True, slots=True)
class SubprocessRunner:
    default_timeout_seconds: float = 600.0
    termination_grace_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.default_timeout_seconds <= 0:
            raise ValueError("Default command timeout must be positive")
        if self.termination_grace_seconds < 0:
            raise ValueError("Termination grace period cannot be negative")

    def run(
        self,
        argv: Sequence[str | os.PathLike[str]],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
        check: bool = True,
    ) -> ProcessResult:
        command = tuple(os.fspath(argument) for argument in argv)
        if not command:
            raise ValueError("Command cannot be empty")

        timeout = self.default_timeout_seconds if timeout_seconds is None else timeout_seconds
        if timeout <= 0:
            raise ValueError("Command timeout must be positive")

        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        start_new_session = os.name == "posix"
        creationflags = (
            int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
        )

        started = perf_counter()
        process = subprocess.Popen(
            command,
            cwd=Path(cwd) if cwd is not None else None,
            env=process_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            start_new_session=start_new_session,
            creationflags=creationflags,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            self._terminate_process_group(process)
            process.communicate()
            raise CommandTimeoutError(command, timeout) from error

        result = ProcessResult(
            argv=command,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            runtime_seconds=perf_counter() - started,
        )
        if check and result.returncode != 0:
            raise CommandFailedError(result)
        return result

    def _terminate_process_group(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return

        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()

        try:
            process.wait(timeout=self.termination_grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass

        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()
