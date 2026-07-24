from dataclasses import FrozenInstanceError

import pytest

import plasmid_oracle as po


def test_plasmid_factory_constructs_the_canonical_object() -> None:
    plasmid = po.plasmid(
        seq="ATGCNN",
        topology="circular",
        source_metadata={"source": "unit-test"},
    )

    assert plasmid.sequence.bases == "ATGCNN"
    assert plasmid.sequence.topology is po.Topology.CIRCULAR
    assert plasmid.annotations == ()
    assert plasmid.characterization == po.Characterization()
    assert plasmid.analysis.mode == "none"
    assert plasmid.analysis.provider_runs == ()
    assert plasmid.source_metadata == {"source": "unit-test"}


def test_plasmid_and_metadata_are_immutable() -> None:
    plasmid = po.plasmid(seq="ATGC", source_metadata={"source": "unit-test"})

    with pytest.raises(FrozenInstanceError):
        plasmid.annotations = ()  # type: ignore[misc]

    with pytest.raises(TypeError):
        plasmid.source_metadata["source"] = "changed"  # type: ignore[index]


def test_annotation_records_normalized_evidence() -> None:
    source = po.AnnotationSource(
        provider="example",
        provider_version="1.0",
        tool_version="2.0",
        database="parts",
        database_version="2026-01",
    )
    annotation = po.Annotation(
        annotation_id="ann-1",
        feature_type="CDS",
        name="example protein",
        location=po.Location.from_bounds(
            2,
            11,
            sequence_length=20,
            topology="circular",
            strand="+",
        ),
        source=source,
        canonical_ids=("ExampleDB:1",),
        integrity=po.Integrity.COMPLETE,
        metrics=po.EvidenceMetrics(identity=0.99, coverage=1.0, score=42.0),
        qualifiers={"translation_table": 11},
    )

    assert annotation.location.length == 9
    assert annotation.canonical_ids == ("ExampleDB:1",)
    assert annotation.metrics.identity == pytest.approx(0.99)
    assert annotation.qualifiers == {"translation_table": 11}

    with pytest.raises(TypeError):
        annotation.qualifiers["translation_table"] = 1  # type: ignore[index]


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_identity_and_coverage_are_fractions(value: float) -> None:
    with pytest.raises(ValueError, match="identity"):
        po.EvidenceMetrics(identity=value)

    with pytest.raises(ValueError, match="coverage"):
        po.EvidenceMetrics(coverage=value)
