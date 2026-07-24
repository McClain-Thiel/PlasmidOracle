from __future__ import annotations

from pathlib import Path

import plasmid_oracle as po


class CountingProvider:
    spec = po.ProviderSpec(name="counting", version="1", modes=("fast",))

    def __init__(self, *, database_version: str = "2026.07") -> None:
        self.database_version = database_version
        self.calls = 0

    def diagnose(self, context: po.ProviderContext) -> po.ProviderDiagnostic:
        return po.ProviderDiagnostic(
            name=self.spec.name,
            available=True,
            provider_version=self.spec.version,
            tool_version="2.1",
            database_versions={"counting-db": self.database_version},
        )

    def run(
        self,
        sequence: po.SequenceInfo,
        context: po.ProviderContext,
    ) -> po.ProviderResult:
        self.calls += 1
        source = po.AnnotationSource(
            provider=self.spec.name,
            provider_version=self.spec.version,
            tool_version="2.1",
            database="counting-db",
            database_version=self.database_version,
        )
        return po.ProviderResult(
            annotations=(
                po.Annotation(
                    annotation_id="counting:1",
                    feature_type="rep_origin",
                    name="counted origin",
                    location=po.Location.from_bounds(
                        2,
                        12,
                        sequence_length=sequence.length,
                        topology=sequence.topology,
                    ),
                    source=source,
                ),
            ),
            tool_version="2.1",
            database_versions={"counting-db": self.database_version},
        )


def _annotate(provider: CountingProvider, cache_dir: Path, *, seq: str = "ATGC" * 20) -> po.Plasmid:
    return po.annotate(
        seq=seq,
        mode="fast",
        providers=(provider,),
        cache=True,
        cache_dir=cache_dir,
    )


def test_provider_cache_reuses_a_versioned_result(tmp_path: Path) -> None:
    provider = CountingProvider()

    first = _annotate(provider, tmp_path)
    second = _annotate(provider, tmp_path)

    assert provider.calls == 1
    assert first.evidence == second.evidence
    assert first.annotations == second.annotations
    assert first.analysis.provider_runs[0].status is po.ProviderStatus.COMPLETED
    assert second.analysis.provider_runs[0].status is po.ProviderStatus.CACHED
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_cache_key_changes_with_sequence_and_database_version(tmp_path: Path) -> None:
    provider = CountingProvider()
    _annotate(provider, tmp_path)
    _annotate(provider, tmp_path, seq="ATGA" * 20)

    updated_provider = CountingProvider(database_version="2026.08")
    _annotate(updated_provider, tmp_path)

    assert provider.calls == 2
    assert updated_provider.calls == 1
    assert len(list(tmp_path.rglob("*.json"))) == 3


def test_corrupt_cache_is_ignored_and_reported(tmp_path: Path) -> None:
    provider = CountingProvider()
    _annotate(provider, tmp_path)
    cache_file = next(tmp_path.rglob("*.json"))
    cache_file.write_text("{not JSON", encoding="utf-8")

    result = _annotate(provider, tmp_path)

    assert provider.calls == 2
    assert result.analysis.provider_runs[0].status is po.ProviderStatus.COMPLETED
    assert any("cache" in warning.casefold() for warning in result.analysis.warnings)
