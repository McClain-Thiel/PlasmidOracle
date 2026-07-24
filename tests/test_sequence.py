from dataclasses import FrozenInstanceError

import pytest

import plasmid_oracle as po


def test_sequence_normalization_preserves_iupac_and_removes_only_whitespace() -> None:
    sequence = po.SequenceInfo.from_raw(" acgt\nRYN\t", topology="circular")

    assert sequence.bases == "ACGTRYN"
    assert sequence.length == 7
    assert sequence.ambiguous_base_count == 3
    assert sequence.gc_fraction == pytest.approx(0.5)
    assert [warning.code for warning in sequence.warnings] == ["ambiguous_bases"]


@pytest.mark.parametrize("raw", ["ATG-XC", "ATGU", "not dna"])
def test_sequence_normalization_rejects_non_dna_characters(raw: str) -> None:
    with pytest.raises(po.InvalidSequenceError, match="Invalid DNA"):
        po.SequenceInfo.from_raw(raw)


def test_sequence_normalization_rejects_empty_input() -> None:
    with pytest.raises(po.InvalidSequenceError, match="empty"):
        po.SequenceInfo.from_raw(" \n\t")


def test_gc_fraction_is_unknown_when_every_base_is_ambiguous() -> None:
    sequence = po.SequenceInfo.from_raw("NNNN")

    assert sequence.gc_fraction is None


def test_circular_canonical_checksum_is_rotation_and_strand_invariant() -> None:
    original = po.SequenceInfo.from_raw("ATGCCGTA", topology="circular")
    rotated = po.SequenceInfo.from_raw("CCGTAATG", topology="circular")
    reverse_complement = po.SequenceInfo.from_raw("TACGGCAT", topology="circular")

    assert original.checksum != rotated.checksum
    assert original.checksum != reverse_complement.checksum
    assert original.canonical_checksum == rotated.canonical_checksum
    assert original.canonical_checksum == reverse_complement.canonical_checksum


def test_linear_canonical_checksum_is_not_rotation_invariant() -> None:
    original = po.SequenceInfo.from_raw("ATGCCGTA", topology="linear")
    rotated = po.SequenceInfo.from_raw("CCGTAATG", topology="linear")

    assert original.canonical_checksum != rotated.canonical_checksum


def test_sequence_info_is_immutable() -> None:
    sequence = po.SequenceInfo.from_raw("ATGC")

    with pytest.raises(FrozenInstanceError):
        sequence.bases = "AAAA"  # type: ignore[misc]
