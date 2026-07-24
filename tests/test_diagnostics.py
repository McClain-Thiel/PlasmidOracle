from __future__ import annotations

import plasmid_oracle as po


def test_fast_mode_diagnostics_report_pyrodigal_ready() -> None:
    report = po.doctor(mode="fast")

    assert report.mode == "fast"
    assert report.ready is True
    assert len(report.providers) == 1
    assert report.providers[0].name == "pyrodigal"
    assert report.providers[0].available is True
    assert report.providers[0].tool_version
