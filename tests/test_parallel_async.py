from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field

import pytest

import plasmid_oracle as po


@dataclass
class ConcurrencyProbe:
    active: int = 0
    maximum: int = 0
    provider_threads: list[int] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def enter(self, threads: int) -> None:
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self.provider_threads.append(threads)

    def exit(self) -> None:
        with self.lock:
            self.active -= 1


class DelayedProvider:
    def __init__(self, name: str, delay: float, probe: ConcurrencyProbe) -> None:
        self.spec = po.ProviderSpec(name=name, version="1", modes=("fast",))
        self.delay = delay
        self.probe = probe

    def run(
        self,
        sequence: po.SequenceInfo,
        context: po.ProviderContext,
    ) -> po.ProviderResult:
        self.probe.enter(context.threads)
        try:
            time.sleep(self.delay)
            return po.ProviderResult(tool_version="test")
        finally:
            self.probe.exit()


class DelayedFailureProvider(DelayedProvider):
    def run(
        self,
        sequence: po.SequenceInfo,
        context: po.ProviderContext,
    ) -> po.ProviderResult:
        self.probe.enter(context.threads)
        try:
            time.sleep(self.delay)
            raise RuntimeError("deliberate parallel failure")
        finally:
            self.probe.exit()


def test_pipeline_runs_providers_concurrently_with_a_total_thread_budget() -> None:
    probe = ConcurrencyProbe()
    providers = (
        DelayedProvider("slow", 0.05, probe),
        DelayedProvider("fast", 0.01, probe),
    )

    plasmid = po.annotate(
        seq="ATGC" * 30,
        mode="fast",
        providers=providers,
        threads=4,
        provider_workers=2,
    )

    assert probe.maximum == 2
    assert probe.provider_threads == [2, 2]
    assert [run.name for run in plasmid.analysis.provider_runs] == ["slow", "fast"]


def test_provider_worker_count_must_fit_the_thread_budget() -> None:
    with pytest.raises(ValueError, match="provider_workers"):
        po.annotate(
            seq="ATGC" * 30,
            mode="fast",
            providers=(),
            threads=2,
            provider_workers=3,
        )


def test_async_annotation_does_not_block_the_event_loop() -> None:
    async def scenario() -> po.Plasmid:
        probe = ConcurrencyProbe()
        task = asyncio.create_task(
            po.annotate_async(
                seq="ATGC" * 30,
                mode="fast",
                providers=(DelayedProvider("delayed", 0.05, probe),),
            )
        )
        await asyncio.sleep(0.005)
        assert not task.done()
        return await task

    plasmid = asyncio.run(scenario())

    assert plasmid.analysis.provider_runs[0].name == "delayed"
    assert plasmid.analysis_complete is True


def test_parallel_failure_manifest_remains_in_provider_order() -> None:
    probe = ConcurrencyProbe()
    providers = (
        DelayedFailureProvider("broken", 0.01, probe),
        DelayedProvider("completed", 0.03, probe),
    )

    with pytest.raises(po.ProviderExecutionError, match="deliberate parallel failure") as caught:
        po.annotate(
            seq="ATGC" * 30,
            mode="fast",
            providers=providers,
            threads=2,
            provider_workers=2,
        )

    assert [run.name for run in caught.value.provider_runs] == ["broken", "completed"]
    assert [run.status for run in caught.value.provider_runs] == [
        po.ProviderStatus.FAILED,
        po.ProviderStatus.COMPLETED,
    ]
