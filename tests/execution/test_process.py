from __future__ import annotations

import sys

import pytest

from plasmid_oracle.execution import (
    CommandFailedError,
    CommandTimeoutError,
    SubprocessRunner,
)


def test_subprocess_runner_captures_output_without_a_shell() -> None:
    runner = SubprocessRunner(default_timeout_seconds=5)

    result = runner.run((sys.executable, "-c", "print('ready')"))

    assert result.argv == (sys.executable, "-c", "print('ready')")
    assert result.returncode == 0
    assert result.stdout == "ready\n"
    assert result.stderr == ""
    assert result.runtime_seconds >= 0


def test_subprocess_runner_merges_explicit_environment_values() -> None:
    runner = SubprocessRunner(default_timeout_seconds=5)

    result = runner.run(
        (
            sys.executable,
            "-c",
            "import os; print(os.environ['PLASMID_ORACLE_RUNNER_TEST'])",
        ),
        env={"PLASMID_ORACLE_RUNNER_TEST": "present"},
    )

    assert result.stdout == "present\n"


def test_subprocess_runner_raises_a_structured_nonzero_error() -> None:
    runner = SubprocessRunner(default_timeout_seconds=5)

    with pytest.raises(CommandFailedError) as caught:
        runner.run(
            (
                sys.executable,
                "-c",
                "import sys; print('bad', file=sys.stderr); raise SystemExit(7)",
            )
        )

    assert caught.value.result.returncode == 7
    assert caught.value.result.stderr == "bad\n"
    assert caught.value.result.argv[0] == sys.executable


def test_subprocess_runner_terminates_timed_out_commands() -> None:
    runner = SubprocessRunner(default_timeout_seconds=0.05)

    with pytest.raises(CommandTimeoutError) as caught:
        runner.run((sys.executable, "-c", "import time; time.sleep(5)"))

    assert caught.value.timeout_seconds == pytest.approx(0.05)
    assert caught.value.argv[0] == sys.executable
