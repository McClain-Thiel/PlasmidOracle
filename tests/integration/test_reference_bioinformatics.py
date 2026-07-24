from __future__ import annotations

import os
from pathlib import Path

import pytest

import plasmid_oracle as po
from plasmid_oracle.model.sequence import reverse_complement

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PLASMID_ORACLE_RUN_INTEGRATION") != "1",
        reason="set PLASMID_ORACLE_RUN_INTEGRATION=1 to run database-backed tests",
    ),
]

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "plasmids" / "pBR322_J01749.1.fasta"


def _sequence() -> str:
    return "".join(
        line.strip()
        for line in _FIXTURE.read_text(encoding="ascii").splitlines()
        if not line.startswith(">")
    )


def _standard(sequence: str, cache_dir: Path) -> po.Plasmid:
    return po.annotate(
        seq=sequence,
        topology="circular",
        mode="standard",
        threads=4,
        provider_workers=4,
        timeout_seconds=900,
        cache=True,
        cache_dir=cache_dir,
    )


def test_standard_mode_resolves_expected_pbr322_biology(tmp_path: Path) -> None:
    plasmid = _standard(_sequence(), tmp_path)

    assert {feature.name for feature in plasmid.amr_genes} == {"blaTEM-1", "tet(C)"}
    assert plasmid.find("rop")
    assert plasmid.find("ori")
    assert plasmid.find("bom")
    assert plasmid.characterization.mobility[0].name == "mobilizable"
    assert any(
        conflict.code == "strand_disagreement"
        for feature in plasmid.find("blaTEM-1")
        for conflict in feature.conflicts
    )
    assert plasmid.analysis_complete is True


def test_bla_deletion_removes_only_the_corresponding_amr_call(tmp_path: Path) -> None:
    sequence = _sequence()
    without_bla = sequence[:3_292] + sequence[4_153:]

    plasmid = _standard(without_bla, tmp_path)

    amr_names = {feature.name for feature in plasmid.amr_genes}
    assert "blaTEM-1" not in amr_names
    assert "tet(C)" in amr_names


def test_standard_biology_survives_rotation_and_reverse_complement(tmp_path: Path) -> None:
    sequence = _sequence()
    variants = (
        sequence,
        sequence[500:] + sequence[:500],
        reverse_complement(sequence),
    )

    plasmids = tuple(_standard(variant, tmp_path) for variant in variants)
    signatures = [
        {
            (
                feature.feature_type,
                feature.name,
                feature.integrity,
                tuple(sorted(feature.providers)),
            )
            for feature in plasmid.annotations
        }
        for plasmid in plasmids
    ]

    assert signatures[1:] == signatures[:1] * 2
