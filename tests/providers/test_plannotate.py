from __future__ import annotations

import plasmid_oracle as po
from plasmid_oracle.providers.plannotate import (
    _plannotate_version,
    parse_plannotate_records,
)


def test_plannotate_records_are_normalized_with_circular_coordinates() -> None:
    sequence = po.SequenceInfo.from_raw("ATGCCGTAGCTA", topology="circular")
    records = [
        {
            "qstart": 2,
            "qend": 8,
            "sseqid": "blaTEM-1",
            "sframe": 1,
            "pident": 99.5,
            "evalue": 1e-40,
            "score": 125.0,
            "abs percmatch": 98.0,
            "qseq": "GCCGTA",
            "db": "snapgene",
            "Feature": "AmpR",
            "Description": "beta-lactamase",
            "Type": "CDS",
            "fragment": False,
        },
        {
            "qstart": 10,
            "qend": 3,
            "sseqid": "ori-wrap",
            "sframe": -1,
            "pident": 97.0,
            "evalue": 1e-12,
            "score": 42.0,
            "abs percmatch": 91.0,
            "qseq": "TAGAT",
            "db": "snapgene",
            "Feature": "wrapped origin",
            "Description": "",
            "Type": "origin of replication",
            "fragment": True,
        },
    ]

    result = parse_plannotate_records(
        records,
        sequence=sequence,
        provider_version="1.0",
        tool_version="1.2.9",
        database_versions={"snapgene": "2021-07-23"},
    )

    assert [annotation.feature_type for annotation in result.annotations] == [
        "CDS",
        "rep_origin",
    ]
    assert result.annotations[0].metrics.identity == 0.995
    assert result.annotations[0].metrics.coverage == 0.98
    assert result.annotations[0].integrity is po.Integrity.COMPLETE
    assert result.annotations[1].location.spans == (
        po.Span(10, 12),
        po.Span(0, 3),
    )
    assert result.annotations[1].location.strand is po.Strand.REVERSE
    assert result.annotations[1].integrity is po.Integrity.PARTIAL


def test_plannotate_empty_output_is_a_valid_result() -> None:
    sequence = po.SequenceInfo.from_raw("ATGC")

    result = parse_plannotate_records(
        [],
        sequence=sequence,
        provider_version="1.0",
        tool_version="1.2.9",
        database_versions={},
    )

    assert result.annotations == ()


def test_plannotate_version_comes_from_distribution_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "plasmid_oracle.providers.plannotate.distribution_version",
        lambda name: "1.2.9",
    )

    assert _plannotate_version() == "1.2.9"
