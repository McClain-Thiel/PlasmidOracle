from __future__ import annotations

from pathlib import Path

import plasmid_oracle as po
from plasmid_oracle.providers.pyrodigal import PyrodigalProvider


def _fixture_sequence() -> str:
    lines = Path("tests/fixtures/bla_tem.fasta").read_text(encoding="ascii").splitlines()
    return "".join(line for line in lines if not line.startswith(">"))


def test_pyrodigal_provider_runs_real_gene_prediction() -> None:
    sequence = po.SequenceInfo.from_raw(_fixture_sequence(), topology="linear")
    provider = PyrodigalProvider()

    result = provider.run(
        sequence,
        po.ProviderContext(mode="fast"),
    )

    assert result.tool_version
    assert result.annotations
    assert all(annotation.feature_type == "CDS" for annotation in result.annotations)
    assert all(annotation.source.provider == "pyrodigal" for annotation in result.annotations)
    assert all(annotation.protein_sequence for annotation in result.annotations)
    assert all(
        annotation.location.sequence_length == sequence.length for annotation in result.annotations
    )


def test_pyrodigal_circular_annotations_stay_within_original_coordinates() -> None:
    sequence = po.SequenceInfo.from_raw(_fixture_sequence(), topology="circular")

    result = PyrodigalProvider().run(
        sequence,
        po.ProviderContext(mode="fast"),
    )

    assert result.annotations
    assert all(
        span.end <= sequence.length
        for annotation in result.annotations
        for span in annotation.location.spans
    )
    assert len({annotation.annotation_id for annotation in result.annotations}) == len(
        result.annotations
    )
