from __future__ import annotations

import plasmid_oracle as po


def _evidence(
    *,
    annotation_id: str,
    provider: str,
    feature_type: str,
    name: str,
    start: int,
    end: int,
    strand: str,
    sequence_length: int = 1_000,
    integrity: po.Integrity = po.Integrity.COMPLETE,
) -> po.Annotation:
    return po.Annotation(
        annotation_id=annotation_id,
        feature_type=feature_type,
        name=name,
        location=po.Location.from_bounds(
            start,
            end,
            sequence_length=sequence_length,
            topology="circular",
            strand=strand,
        ),
        source=po.AnnotationSource(provider=provider, provider_version="1"),
        integrity=integrity,
    )


def test_resolver_groups_compatible_coding_evidence() -> None:
    evidence = (
        _evidence(
            annotation_id="pyrodigal:1",
            provider="pyrodigal",
            feature_type="CDS",
            name="predicted CDS",
            start=85,
            end=1_276,
            strand="+",
            sequence_length=4_361,
        ),
        _evidence(
            annotation_id="plannotate:1",
            provider="plannotate",
            feature_type="CDS",
            name="tetA",
            start=85,
            end=1_273,
            strand="+",
            sequence_length=4_361,
        ),
        _evidence(
            annotation_id="amrfinder:1",
            provider="amrfinderplus",
            feature_type="antimicrobial_resistance_gene",
            name="tet(C)",
            start=85,
            end=1_273,
            strand="+",
            sequence_length=4_361,
        ),
    )

    resolved = po.resolve_annotations(evidence)

    assert len(resolved) == 1
    feature = resolved[0]
    assert feature.name == "tet(C)"
    assert feature.aliases == ("tetA",)
    assert feature.feature_type == "antimicrobial_resistance_gene"
    assert feature.location.start == 85
    assert feature.location.end == 1_273
    assert feature.location.strand is po.Strand.FORWARD
    assert feature.status is po.ResolutionStatus.SUPPORTED
    assert feature.providers == ("amrfinderplus", "plannotate", "pyrodigal")
    assert feature.conflicts == ()
    assert tuple(call.annotation_id for call in feature.evidence) == (
        "amrfinder:1",
        "plannotate:1",
        "pyrodigal:1",
    )


def test_resolver_preserves_and_flags_strand_disagreement() -> None:
    evidence = (
        _evidence(
            annotation_id="pyrodigal:1",
            provider="pyrodigal",
            feature_type="CDS",
            name="predicted CDS",
            start=100,
            end=300,
            strand="-",
        ),
        _evidence(
            annotation_id="plannotate:1",
            provider="plannotate",
            feature_type="CDS",
            name="AmpR",
            start=100,
            end=300,
            strand="+",
        ),
        _evidence(
            annotation_id="amrfinder:1",
            provider="amrfinderplus",
            feature_type="antimicrobial_resistance_gene",
            name="blaTEM-1",
            start=103,
            end=300,
            strand="-",
        ),
    )

    feature = po.resolve_annotations(evidence)[0]

    assert feature.name == "blaTEM-1"
    assert feature.location.start == 100
    assert feature.location.end == 300
    assert feature.location.strand is po.Strand.REVERSE
    assert feature.status is po.ResolutionStatus.CONFLICTED
    assert [conflict.code for conflict in feature.conflicts] == ["strand_disagreement"]
    assert feature.conflicts[0].evidence_ids == (
        "amrfinder:1",
        "plannotate:1",
        "pyrodigal:1",
    )


def test_resolver_marks_single_source_and_keeps_unrelated_features_separate() -> None:
    evidence = (
        _evidence(
            annotation_id="plannotate:promoter",
            provider="plannotate",
            feature_type="promoter",
            name="tet promoter",
            start=80,
            end=120,
            strand="+",
        ),
        _evidence(
            annotation_id="plannotate:cds",
            provider="plannotate",
            feature_type="CDS",
            name="tetA",
            start=85,
            end=400,
            strand="+",
        ),
    )

    resolved = po.resolve_annotations(evidence)

    assert [feature.feature_type for feature in resolved] == ["promoter", "CDS"]
    assert all(feature.status is po.ResolutionStatus.SINGLE_SOURCE for feature in resolved)


def test_resolution_is_deterministic_for_input_order() -> None:
    evidence = (
        _evidence(
            annotation_id="provider-b:1",
            provider="provider-b",
            feature_type="CDS",
            name="named feature",
            start=100,
            end=300,
            strand="+",
        ),
        _evidence(
            annotation_id="provider-a:1",
            provider="provider-a",
            feature_type="CDS",
            name="predicted CDS",
            start=100,
            end=300,
            strand="+",
        ),
    )

    forward = po.resolve_annotations(evidence)
    reverse = po.resolve_annotations(tuple(reversed(evidence)))

    assert forward == reverse
    assert forward[0].annotation_id == "resolved:0001"


def test_resolver_absorbs_a_contained_partial_origin_fragment() -> None:
    partial = _evidence(
        annotation_id="amrfinder:partial",
        provider="amrfinderplus",
        feature_type="antimicrobial_resistance_gene",
        name="tet(C)",
        start=2,
        end=773,
        strand="+",
        sequence_length=4_361,
        integrity=po.Integrity.PARTIAL,
    )
    complete = po.Annotation(
        annotation_id="amrfinder:complete",
        feature_type="antimicrobial_resistance_gene",
        name="tet(C)",
        location=po.Location.from_bounds(
            3_946,
            773,
            sequence_length=4_361,
            topology="circular",
            strand="+",
        ),
        source=po.AnnotationSource(provider="amrfinderplus"),
        integrity=po.Integrity.COMPLETE,
        metrics=po.EvidenceMetrics(identity=1.0, coverage=1.0),
    )

    resolved = po.resolve_annotations((partial, complete))

    assert len(resolved) == 1
    assert resolved[0].location.wraps_origin is True
    assert resolved[0].integrity is po.Integrity.COMPLETE
    assert resolved[0].conflicts == ()
