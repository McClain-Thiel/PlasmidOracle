from __future__ import annotations

import sys
from types import ModuleType

import pytest

import plasmid_oracle as po


class ReadableProvider:
    spec = po.ProviderSpec(name="readable", version="1", modes=("fast",))

    def run(
        self,
        sequence: po.SequenceInfo,
        context: po.ProviderContext,
    ) -> po.ProviderResult:
        source = po.AnnotationSource(provider=self.spec.name, provider_version=self.spec.version)
        return po.ProviderResult(
            annotations=(
                po.Annotation(
                    annotation_id="readable:amr",
                    feature_type="antimicrobial_resistance_gene",
                    name="blaTEST-1",
                    location=po.Location.from_bounds(
                        3,
                        30,
                        sequence_length=sequence.length,
                        topology=sequence.topology,
                        strand="+",
                    ),
                    source=source,
                ),
                po.Annotation(
                    annotation_id="readable:ori",
                    feature_type="rep_origin",
                    name="test origin",
                    location=po.Location.from_bounds(
                        40,
                        70,
                        sequence_length=sequence.length,
                        topology=sequence.topology,
                    ),
                    source=source,
                ),
            ),
        )


@pytest.fixture
def readable_plasmid() -> po.Plasmid:
    return po.annotate(
        seq="ATGCGTAC" * 20,
        mode="fast",
        providers=(ReadableProvider(),),
        source_metadata={"id": "pReadable"},
    )


def test_plasmid_exposes_raw_evidence_and_resolved_annotations(
    readable_plasmid: po.Plasmid,
) -> None:
    assert len(readable_plasmid.evidence) == 2
    assert len(readable_plasmid.annotations) == 2
    assert isinstance(readable_plasmid.evidence[0], po.Annotation)
    assert isinstance(readable_plasmid.annotations[0], po.ResolvedAnnotation)


def test_plasmid_query_helpers(readable_plasmid: po.Plasmid) -> None:
    assert [feature.name for feature in readable_plasmid.amr_genes] == ["blaTEST-1"]
    assert [feature.name for feature in readable_plasmid.find("origin")] == ["test origin"]
    assert [feature.name for feature in readable_plasmid.features(feature_type="rep_origin")] == [
        "test origin"
    ]
    assert readable_plasmid.conflicts == ()
    assert readable_plasmid.provider_status == {"readable": po.ProviderStatus.COMPLETED}
    assert readable_plasmid.analysis_complete is True


def test_plasmid_summary_is_readable_and_does_not_print_the_sequence(
    readable_plasmid: po.Plasmid,
) -> None:
    summary = readable_plasmid.summary()

    assert "pReadable" in summary
    assert "160 bp" in summary
    assert "2 resolved annotations from 2 evidence calls" in summary
    assert "blaTEST-1" in summary
    assert "test origin" in summary
    assert readable_plasmid.sequence.bases not in summary
    assert str(readable_plasmid) == summary
    assert readable_plasmid.sequence.bases not in repr(readable_plasmid)
    assert repr(readable_plasmid) == (
        "Plasmid(id='pReadable', length=160, topology='circular', "
        "annotations=2, evidence=2, mode='fast')"
    )


def test_plasmid_dataframe_contains_resolved_features(readable_plasmid: po.Plasmid) -> None:
    frame = readable_plasmid.to_dataframe()

    assert list(frame["name"]) == ["blaTEST-1", "test origin"]
    assert list(frame["status"]) == ["single_source", "single_source"]
    assert list(frame["providers"]) == ["readable", "readable"]


def test_plasmid_dataframe_rejects_an_incomplete_pandas_installation(
    readable_plasmid: po.Plasmid,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "pandas", ModuleType("pandas"))

    with pytest.raises(RuntimeError, match="complete pandas installation"):
        readable_plasmid.to_dataframe()
