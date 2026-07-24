from __future__ import annotations

import json
from pathlib import Path

import pytest

import plasmid_oracle as po

_PBR322 = "".join(
    line.strip()
    for line in (Path(__file__).parent / "fixtures/plasmids/pBR322_J01749.1.fasta")
    .read_text(encoding="utf-8")
    .splitlines()
    if not line.startswith(">")
)


def test_plasmid_serialization_is_stable_and_json_compatible() -> None:
    plasmid = po.annotate(
        seq=_PBR322,
        topology="circular",
        mode="fast",
        source_metadata={"id": "p-test", "tags": ["fixture", "small"]},
    )

    payload = po.to_dict(plasmid)

    assert payload["schema_version"] == "3"
    assert payload["sequence"]["topology"] == "circular"
    assert payload["sequence"]["bases"] == plasmid.sequence.bases
    assert payload["source_metadata"]["tags"] == ["fixture", "small"]
    assert payload["analysis"]["provider_runs"][0]["name"] == "pyrodigal"
    assert payload["evidence"]
    assert "evidence_id" in payload["evidence"][0]
    assert payload["annotations"]
    assert "evidence_ids" in payload["annotations"][0]
    assert "evidence" not in payload["annotations"][0]
    assert json.loads(po.to_json(plasmid)) == payload


def test_serialization_preserves_wrapped_location_spans() -> None:
    source = po.AnnotationSource(provider="fixture")
    annotation = po.Annotation(
        annotation_id="wrapped",
        feature_type="CDS",
        name="wrapped CDS",
        location=po.Location.from_bounds(
            90,
            12,
            sequence_length=100,
            topology="circular",
        ),
        source=source,
    )
    plasmid = po.Plasmid(
        sequence=po.SequenceInfo.from_raw("A" * 100),
        evidence=(annotation,),
        annotations=po.resolve_annotations((annotation,)),
        characterization=po.Characterization(),
        source_metadata={},
        analysis=po.AnalysisManifest(pipeline_version="test", mode="test"),
    )

    location = po.to_dict(plasmid)["annotations"][0]["location"]

    assert location["spans"] == [
        {"start": 90, "end": 100},
        {"start": 0, "end": 12},
    ]


def test_json_round_trip_restores_the_canonical_object() -> None:
    original = po.annotate(
        seq=_PBR322,
        topology="circular",
        mode="fast",
        source_metadata={"id": "round-trip"},
    )

    restored = po.from_json(po.to_json(original))

    assert restored == original
    assert restored.annotations[0].evidence[0] is restored.evidence[0]


def test_schema_one_payload_is_migrated_as_raw_evidence() -> None:
    original = po.annotate(seq=_PBR322, mode="fast")
    legacy = po.to_dict(original)
    legacy["schema_version"] = "1"
    legacy["annotations"] = legacy.pop("evidence")

    restored = po.from_dict(legacy)

    assert restored.evidence == original.evidence
    assert restored.annotations == original.annotations


def test_deserialization_rejects_unknown_evidence_references() -> None:
    original = po.annotate(seq=_PBR322, mode="fast")
    payload = po.to_dict(original)
    payload["annotations"][0]["evidence_ids"] = ["missing"]

    with pytest.raises(po.InvalidSerializedPlasmidError, match="missing"):
        po.from_dict(payload)
