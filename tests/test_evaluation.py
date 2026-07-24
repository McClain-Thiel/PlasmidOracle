from __future__ import annotations

import json

import pytest

import plasmid_oracle as po


def _annotation(
    annotation_id: str,
    feature_type: str,
    name: str,
    *,
    start: int = 5,
    end: int = 35,
    integrity: po.Integrity = po.Integrity.COMPLETE,
    qualifiers: dict[str, object] | None = None,
) -> po.Annotation:
    return po.Annotation(
        annotation_id=annotation_id,
        feature_type=feature_type,
        name=name,
        location=po.Location.from_bounds(
            start,
            end,
            sequence_length=120,
            topology="circular",
        ),
        source=po.AnnotationSource(provider="fixture", provider_version="1"),
        integrity=integrity,
        metrics=po.EvidenceMetrics(identity=0.99, coverage=1.0),
        qualifiers=qualifiers or {},
    )


def _plasmid(
    evidence: tuple[po.Annotation, ...],
    *,
    sequence: str = "ATCGTGCA" + "ATGC" * 28,
    topology: str = "circular",
    provider_status: po.ProviderStatus = po.ProviderStatus.COMPLETED,
) -> po.Plasmid:
    return po.Plasmid(
        sequence=po.SequenceInfo.from_raw(sequence, topology=topology),
        evidence=evidence,
        annotations=po.resolve_annotations(evidence),
        characterization=po.Characterization(),
        source_metadata={"id": "evaluation-fixture"},
        analysis=po.AnalysisManifest(
            pipeline_version="test",
            mode="test",
            provider_runs=(
                po.ProviderRun(
                    name="fixture",
                    status=provider_status,
                    provider_version="1",
                    error="fixture provider failed"
                    if provider_status is po.ProviderStatus.FAILED
                    else None,
                ),
            ),
        ),
    )


def test_default_validity_does_not_require_a_selection_marker() -> None:
    plasmid = _plasmid(
        (
            _annotation(
                "fixture:ori",
                "rep_origin",
                "novel replication origin",
            ),
        )
    )

    report = po.evaluate(plasmid)

    assert report.scope is po.EvaluationScope.VALIDITY
    assert report.preset == "plasmid_candidate"
    assert report.status is po.EvaluationStatus.PASS
    assert report.finding("sequence_evaluable").status is po.EvaluationStatus.PASS
    assert report.finding("plasmid_evidence").status is po.EvaluationStatus.PASS


def test_lab_vector_utility_requires_selection_marker() -> None:
    plasmid = _plasmid(
        (
            _annotation(
                "fixture:ori",
                "rep_origin",
                "novel replication origin",
            ),
        )
    )

    report = po.evaluate(plasmid, preset="lab_vector")

    assert report.scope is po.EvaluationScope.UTILITY
    assert report.status is po.EvaluationStatus.FAIL
    assert report.finding("has_replication_component").status is po.EvaluationStatus.PASS
    assert report.finding("has_selection_component").status is po.EvaluationStatus.FAIL


def test_threshold_configuration_can_make_utility_more_strict() -> None:
    plasmid = _plasmid(
        (
            _annotation(
                "fixture:ori",
                "rep_origin",
                "borderline origin",
                qualifiers={"Description": "low confidence origin"},
            ),
            po.Annotation(
                annotation_id="fixture:amp",
                feature_type="antimicrobial_resistance_gene",
                name="blaTEM-1",
                location=po.Location.from_bounds(
                    40,
                    90,
                    sequence_length=120,
                    topology="circular",
                ),
                source=po.AnnotationSource(provider="fixture", provider_version="1"),
                integrity=po.Integrity.COMPLETE,
                metrics=po.EvidenceMetrics(identity=0.86, coverage=0.91),
                qualifiers={"Description": "confers resistance to ampicillin"},
            ),
        )
    )

    default = po.evaluate(plasmid, preset="lab_vector")
    strict = po.evaluate(
        plasmid,
        preset="lab_vector",
        config=po.EvaluationConfig(min_identity=0.95, min_coverage=0.95),
    )

    assert default.status is po.EvaluationStatus.PASS
    assert strict.status is po.EvaluationStatus.FAIL
    assert strict.finding("has_selection_component").status is po.EvaluationStatus.FAIL


def test_failed_provider_keeps_absence_based_requirements_unknown() -> None:
    plasmid = _plasmid((), topology="linear", provider_status=po.ProviderStatus.FAILED)

    report = po.evaluate(plasmid, preset="replicative_plasmid")

    assert report.status is po.EvaluationStatus.UNKNOWN
    assert report.finding("has_replication_component").status is po.EvaluationStatus.UNKNOWN


def test_requirement_fidelity_is_independent_from_baseline_validity() -> None:
    plasmid = _plasmid(
        (
            _annotation("fixture:ori", "rep_origin", "ColE1/pMB1 origin"),
            _annotation(
                "fixture:tet",
                "antimicrobial_resistance_gene",
                "tet(C)",
                start=40,
                end=90,
                qualifiers={"Description": "confers resistance to tetracycline"},
            ),
        )
    )
    requirements = po.RequirementSet(
        preset=None,
        requirements=(
            po.Requirement(
                check="selection_marker",
                value="ampicillin",
                source_text="amp resistant",
                confidence=0.92,
                canonicalization_status="canonical",
            ),
            po.Requirement(
                check="payload_sequence",
                value="ATCGTGCA",
                source_text="expressing ATCGTGCA",
                confidence=0.88,
                canonicalization_status="literal",
            ),
        ),
    )

    validity = po.evaluate(plasmid)
    fidelity = po.evaluate(plasmid, requirements=requirements)

    assert validity.status is po.EvaluationStatus.PASS
    assert fidelity.scope is po.EvaluationScope.FIDELITY
    assert fidelity.status is po.EvaluationStatus.FAIL
    assert fidelity.finding("selection_marker").status is po.EvaluationStatus.FAIL
    assert fidelity.finding("payload_sequence").status is po.EvaluationStatus.PASS


def test_requirement_schema_is_json_compatible_and_restricts_llm_outputs() -> None:
    schema = po.requirement_schema()

    json.dumps(schema)
    assert "lab_vector" in schema["properties"]["preset"]["enum"]  # type: ignore[index]
    requirement_item = schema["properties"]["requirements"]["items"]  # type: ignore[index]
    assert "selection_marker" in requirement_item["properties"]["check"]["enum"]
    assert requirement_item["additionalProperties"] is False
    assert {
        "check",
        "value",
        "source_text",
        "confidence",
        "canonicalization_status",
        "ambiguities",
    } <= set(requirement_item["required"])


def test_requirements_from_dict_validates_model_output() -> None:
    parsed = po.requirements_from_dict(
        {
            "preset": "lab_vector",
            "requirements": [
                {
                    "check": "selection_marker",
                    "value": "ampicillin",
                    "source_text": "amp resistant",
                    "confidence": 0.9,
                    "canonicalization_status": "canonical",
                    "ambiguities": [],
                }
            ],
        }
    )

    assert parsed.preset == "lab_vector"
    assert parsed.requirements[0].check == "selection_marker"
    assert parsed.requirements[0].value == "ampicillin"

    with pytest.raises(ValueError, match="Unsupported requirement check"):
        po.requirements_from_dict(
            {
                "preset": None,
                "requirements": [
                    {
                        "check": "invented_check",
                        "value": None,
                        "source_text": "anything",
                        "confidence": None,
                        "canonicalization_status": "unresolved",
                        "ambiguities": [],
                    }
                ],
            }
        )
