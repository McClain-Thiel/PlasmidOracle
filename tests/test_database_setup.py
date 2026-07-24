from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from plasmid_oracle import ProviderUnavailableError
from plasmid_oracle.databases import setup
from plasmid_oracle.execution import ProcessResult


class SetupRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, **kwargs) -> ProcessResult:
        del kwargs
        command = tuple(str(argument) for argument in argv)
        self.calls.append(command)
        return ProcessResult(
            argv=command,
            returncode=0,
            stdout="",
            stderr="",
            runtime_seconds=0.1,
        )


def test_amrfinder_setup_uses_the_upstream_update_command() -> None:
    runner = SetupRunner()

    result = setup(
        "amrfinderplus",
        runner=runner,
        executable_resolver=lambda executable: f"/tools/{executable}",
    )

    assert runner.calls == [("/tools/amrfinder", "--update")]
    assert result.component == "amrfinderplus"


def test_amrfinder_force_setup_uses_the_upstream_force_update_command() -> None:
    runner = SetupRunner()

    setup(
        "amrfinderplus",
        force=True,
        runner=runner,
        executable_resolver=lambda executable: f"/tools/{executable}",
    )

    assert runner.calls == [("/tools/amrfinder", "--force_update")]


def test_mob_setup_requires_and_populates_an_explicit_directory(
    tmp_path: Path,
) -> None:
    runner = SetupRunner()
    database_dir = tmp_path / "mob-database"

    result = setup(
        "mob_suite",
        runner=runner,
        mob_database_dir=database_dir,
        executable_resolver=lambda executable: f"/tools/{executable}",
    )

    assert runner.calls == [
        (
            "/tools/mob_init",
            "--database_directory",
            str(database_dir),
        )
    ]
    assert result.path == database_dir


def test_mob_setup_accepts_the_configured_database_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runner = SetupRunner()
    database_dir = tmp_path / "mob-database"
    monkeypatch.setenv("PLASMID_ORACLE_MOB_DATABASE", str(database_dir))

    result = setup(
        "mob",
        runner=runner,
        executable_resolver=lambda executable: f"/tools/{executable}",
    )

    assert result.path == database_dir


def test_mob_setup_requires_a_database_directory(monkeypatch) -> None:
    monkeypatch.delenv("PLASMID_ORACLE_MOB_DATABASE", raising=False)

    with pytest.raises(ValueError, match="MOB-suite setup requires"):
        setup("mob_suite", runner=SetupRunner())


def test_plannotate_setup_is_explicit_and_restores_the_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_dir = tmp_path / "BLAST_dbs"
    calls: list[bool] = []

    def download_db(*, force: bool) -> str:
        assert os.environ["PLANNOTATE_AUTO_DOWNLOAD"] == "1"
        calls.append(force)
        return str(database_dir)

    resources = SimpleNamespace(download_db=download_db)
    setup_module = importlib.import_module("plasmid_oracle.databases.setup")
    monkeypatch.setenv("PLANNOTATE_AUTO_DOWNLOAD", "original")
    monkeypatch.setattr(setup_module.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(setup_module.importlib, "import_module", lambda name: resources)

    result = setup("plannotate", force=True)

    assert calls == [True]
    assert result.path == database_dir
    assert os.environ["PLANNOTATE_AUTO_DOWNLOAD"] == "original"


def test_plannotate_setup_explains_the_missing_extra(monkeypatch) -> None:
    setup_module = importlib.import_module("plasmid_oracle.databases.setup")
    monkeypatch.setattr(setup_module.importlib.util, "find_spec", lambda name: None)

    with pytest.raises(ProviderUnavailableError, match="plannotate"):
        setup("plannotate")


def test_unknown_database_component_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown database component"):
        setup("comparison")
