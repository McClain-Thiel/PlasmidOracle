from __future__ import annotations

import hashlib
import json
from pathlib import Path

import plasmid_oracle as po
from plasmid_oracle.model.sequence import reverse_complement

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "plasmids"


def _sequence_from_fasta(path: Path) -> tuple[str, str]:
    lines = path.read_text(encoding="ascii").splitlines()
    assert lines and lines[0].startswith(">")
    return lines[0][1:].split(maxsplit=1)[0], "".join(lines[1:])


def test_reference_plasmid_fixtures_match_their_provenance_manifest() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))

    for record in manifest["records"]:
        path = FIXTURE_DIR / record["file"]
        accession, sequence = _sequence_from_fasta(path)
        normalized = po.SequenceInfo.from_raw(
            sequence,
            topology=record["topology"],
        )

        assert accession == record["accession"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["file_sha256"]
        assert normalized.length == record["length"]
        assert normalized.checksum == record["sequence_sha256"]
        assert normalized.canonical_checksum == record["canonical_sha256"]
        assert normalized.ambiguous_base_count == 0


def test_fast_mode_recovers_the_curated_pbr322_coding_features() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    record = next(item for item in manifest["records"] if item["name"] == "pBR322")
    _, sequence = _sequence_from_fasta(FIXTURE_DIR / record["file"])

    plasmid = po.annotate(
        seq=sequence,
        topology="circular",
        mode="fast",
        source_metadata={"accession": record["accession"]},
    )

    predicted_locations = {
        (
            annotation.location.start,
            annotation.location.end,
            annotation.location.strand.value,
        )
        for annotation in plasmid.annotations
    }
    expected_locations = {
        (feature["start"], feature["end"], feature["strand"])
        for feature in record["ground_truth_features"]
    }

    assert expected_locations <= predicted_locations
    assert plasmid.analysis.provider_runs[0].status is po.ProviderStatus.COMPLETED


def test_fast_annotation_is_invariant_to_rotation_and_reverse_complement() -> None:
    _, sequence = _sequence_from_fasta(FIXTURE_DIR / "pBR322_J01749.1.fasta")
    variants = (
        sequence,
        sequence[500:] + sequence[:500],
        reverse_complement(sequence),
    )

    plasmids = tuple(
        po.annotate(seq=variant, topology="circular", mode="fast") for variant in variants
    )

    assert len({plasmid.sequence.canonical_checksum for plasmid in plasmids}) == 1
    protein_sets = [
        sorted(
            annotation.protein_sequence
            for annotation in plasmid.evidence
            if annotation.protein_sequence is not None
        )
        for plasmid in plasmids
    ]
    assert protein_sets[1:] == protein_sets[:1] * 2
