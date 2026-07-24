import pytest

import plasmid_oracle as po


class ExampleProvider:
    spec = po.ProviderSpec(
        name="example",
        version="1.2.3",
        modes=("fast", "standard"),
    )

    def run(
        self,
        sequence: po.SequenceInfo,
        context: po.ProviderContext,
    ) -> po.ProviderResult:
        assert context.mode == "fast"
        source = po.AnnotationSource(
            provider=self.spec.name,
            provider_version=self.spec.version,
            database="example-db",
            database_version="2026.07",
        )
        annotation = po.Annotation(
            annotation_id="example:feature:1",
            feature_type="rep_origin",
            name="Example origin",
            location=po.Location.from_bounds(
                2,
                8,
                sequence_length=sequence.length,
                topology=sequence.topology,
            ),
            source=source,
        )
        replicon = po.CharacterizationCall(
            name="Example",
            source=source,
            confidence=0.95,
        )
        return po.ProviderResult(
            annotations=(annotation,),
            characterization=po.Characterization(replicons=(replicon,)),
            database_versions={"example-db": "2026.07"},
            warnings=("example warning",),
        )


class BrokenProvider:
    spec = po.ProviderSpec(name="broken", version="0.1", modes=("fast",))

    def run(
        self,
        sequence: po.SequenceInfo,
        context: po.ProviderContext,
    ) -> po.ProviderResult:
        raise RuntimeError("tool exited with code 2")


class UnavailableProvider:
    spec = po.ProviderSpec(name="unavailable", version="0.1", modes=("fast",))

    def run(
        self,
        sequence: po.SequenceInfo,
        context: po.ProviderContext,
    ) -> po.ProviderResult:
        raise po.ProviderUnavailableError("required database is not installed")


class DuplicateEvidenceProvider:
    spec = po.ProviderSpec(name="duplicate", version="1", modes=("fast",))

    def run(
        self,
        sequence: po.SequenceInfo,
        context: po.ProviderContext,
    ) -> po.ProviderResult:
        annotation = po.Annotation(
            annotation_id="duplicate:1",
            feature_type="CDS",
            name="duplicate",
            location=po.Location.from_bounds(
                1,
                10,
                sequence_length=sequence.length,
                topology=sequence.topology,
            ),
            source=po.AnnotationSource(provider="duplicate"),
        )
        return po.ProviderResult(annotations=(annotation, annotation))


def test_annotate_runs_injected_providers_and_builds_a_manifest() -> None:
    plasmid = po.annotate(
        seq="ATGCCGTAGCTA",
        topology="circular",
        mode="fast",
        providers=(ExampleProvider(),),
        source_metadata={"id": "p-test"},
    )

    assert len(plasmid.annotations) == 1
    assert plasmid.annotations[0].name == "Example origin"
    assert plasmid.characterization.replicons[0].name == "Example"
    assert plasmid.source_metadata == {"id": "p-test"}
    assert plasmid.analysis.mode == "fast"
    assert len(plasmid.analysis.provider_runs) == 1

    run = plasmid.analysis.provider_runs[0]
    assert run.name == "example"
    assert run.status is po.ProviderStatus.COMPLETED
    assert run.provider_version == "1.2.3"
    assert run.database_versions == {"example-db": "2026.07"}
    assert run.warnings == ("example warning",)
    assert run.runtime_seconds >= 0


def test_annotate_raises_a_typed_error_for_provider_failure_by_default() -> None:
    with pytest.raises(po.ProviderExecutionError, match="broken") as caught:
        po.annotate(
            seq="ATGCCGTAGCTA",
            mode="fast",
            providers=(BrokenProvider(),),
        )

    assert caught.value.provider_name == "broken"
    assert caught.value.provider_runs[-1].status is po.ProviderStatus.FAILED
    assert "tool exited with code 2" in caught.value.provider_runs[-1].error


def test_tolerant_annotation_records_failure_and_returns_partial_result() -> None:
    plasmid = po.annotate(
        seq="ATGCCGTAGCTA",
        mode="fast",
        providers=(BrokenProvider(), ExampleProvider()),
        strict=False,
    )

    assert [run.status for run in plasmid.analysis.provider_runs] == [
        po.ProviderStatus.FAILED,
        po.ProviderStatus.COMPLETED,
    ]
    assert len(plasmid.annotations) == 1


def test_provider_is_skipped_when_it_does_not_support_the_selected_mode() -> None:
    plasmid = po.annotate(
        seq="ATGCCGTAGCTA",
        mode="deep",
        providers=(ExampleProvider(),),
    )

    assert plasmid.annotations == ()
    assert plasmid.analysis.provider_runs[0].status is po.ProviderStatus.SKIPPED


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="mode"):
        po.annotate(seq="ATGC", mode="turbo")


def test_unavailable_provider_has_a_distinct_manifest_status() -> None:
    plasmid = po.annotate(
        seq="ATGCCGTAGCTA",
        mode="fast",
        providers=(UnavailableProvider(),),
        strict=False,
    )

    assert plasmid.analysis.provider_runs[0].status is po.ProviderStatus.UNAVAILABLE
    assert "database" in plasmid.analysis.provider_runs[0].error


def test_fast_mode_uses_the_builtin_pyrodigal_provider_by_default() -> None:
    plasmid = po.annotate(
        seq="ATGCCGTAGCTA" * 20,
        mode="fast",
    )

    assert [run.name for run in plasmid.analysis.provider_runs] == ["pyrodigal"]


def test_minimal_is_the_default_no_database_mode() -> None:
    plasmid = po.annotate(seq="ATGCCGTAGCTA" * 20)

    assert plasmid.analysis.mode == "minimal"
    assert [run.name for run in plasmid.analysis.provider_runs] == ["pyrodigal"]


def test_duplicate_provider_evidence_ids_are_rejected() -> None:
    with pytest.raises(po.ProviderExecutionError, match="duplicate annotation ID"):
        po.annotate(
            seq="ATGC" * 20,
            mode="fast",
            providers=(DuplicateEvidenceProvider(),),
        )
