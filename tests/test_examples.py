from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_evaluation_example_runs_without_external_databases() -> None:
    root = Path(__file__).parents[1]

    completed = subprocess.run(
        [sys.executable, str(root / "examples" / "evaluate_plasmid.py")],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Validity" in completed.stdout
    assert "Lab vector utility" in completed.stdout
    assert "Prompt fidelity" in completed.stdout
    assert "payload_sequence: fail" in completed.stdout
